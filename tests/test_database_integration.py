"""Comprehensive test suite for PostgreSQL, SQLAlchemy, Alembic, Repositories, Services, and API integration."""

from datetime import datetime, timezone
import os
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agent.api import app
from agent.db.config import normalize_database_url
from agent.db.database import Base, build_engine, get_db, get_db_context
from agent.db.models import (
    AgentRun,
    Conversation,
    ExecutionAction,
    Memory,
    Message,
    Project,
    User,
    Workspace,
    WorkspaceArtifact,
)
from agent.db.repositories import (
    AgentRunRepository,
    ConversationRepository,
    ExecutionActionRepository,
    MemoryRepository,
    ProjectRepository,
    UserRepository,
    WorkspaceArtifactRepository,
    WorkspaceRepository,
)
from agent.db.repositories.execution_action_repository import _sanitize_data
from agent.db.services import AgentRunService, ProjectOwnershipError, ProjectService


class DatabaseEngineAndConfigTests(unittest.TestCase):
    """Test engine builder, configuration normalization, and connection pooling."""

    def test_normalize_database_url(self) -> None:
        # 1. Empty fallback
        fallback = normalize_database_url("")
        self.assertTrue(fallback.startswith("sqlite:///"))

        # 2. postgres:// conversion to postgresql+psycopg://
        pg_old = "postgres://user:pass@localhost:5432/dbname"
        self.assertEqual(
            normalize_database_url(pg_old),
            "postgresql+psycopg://user:pass@localhost:5432/dbname",
        )

        # 3. bare postgresql:// conversion
        pg_bare = "postgresql://user:pass@localhost:5432/dbname"
        self.assertEqual(
            normalize_database_url(pg_bare),
            "postgresql+psycopg://user:pass@localhost:5432/dbname",
        )

        # 4. already qualified driver preserved
        pg_qualified = "postgresql+psycopg2://user:pass@localhost:5432/dbname"
        self.assertEqual(normalize_database_url(pg_qualified), pg_qualified)

    def test_build_engine_sqlite_in_memory(self) -> None:
        engine = build_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            self.assertEqual(result, 1)
        engine.dispose()

    def test_live_postgresql_alembic_full_cycle(self) -> None:
        """Test Alembic migrations against PostgreSQL when Docker database is available."""
        pg_port = os.getenv("POSTGRES_PORT", "5433")
        admin_conn_str = f"postgresql://rorak:rorak_secret_dev@127.0.0.1:{pg_port}/rorak_db"
        import psycopg
        from alembic import command
        from alembic.config import Config

        try:
            with psycopg.connect(admin_conn_str, connect_timeout=2) as conn:
                pass
        except Exception:
            self.skipTest("Live PostgreSQL Docker service not accessible on port " + pg_port)

        test_db_name = f"test_alembic_{uuid4().hex[:8]}"
        with psycopg.connect(admin_conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {test_db_name}")

        test_db_url = f"postgresql+psycopg://rorak:rorak_secret_dev@127.0.0.1:{pg_port}/{test_db_name}"
        try:
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)
            old_db_env = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = test_db_url

            # 1. Upgrade to head
            command.upgrade(alembic_cfg, "head")

            # 2. Check schema
            pg_engine = build_engine(test_db_url)
            with pg_engine.connect() as conn:
                tables = conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                ).scalars().all()
                self.assertIn("users", tables)
                self.assertIn("projects", tables)
                self.assertIn("workspaces", tables)
                self.assertIn("agent_runs", tables)
                self.assertIn("execution_actions", tables)
                self.assertIn("workspace_artifacts", tables)
                self.assertIn("alembic_version", tables)
            pg_engine.dispose()

            # 3. Downgrade to base
            command.downgrade(alembic_cfg, "base")

            with psycopg.connect(f"postgresql://rorak:rorak_secret_dev@127.0.0.1:{pg_port}/{test_db_name}") as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                    remaining = [r[0] for r in cur.fetchall()]
                    self.assertNotIn("projects", remaining)
                    self.assertNotIn("agent_runs", remaining)

            if old_db_env:
                os.environ["DATABASE_URL"] = old_db_env
            else:
                os.environ.pop("DATABASE_URL", None)

        finally:
            with psycopg.connect(admin_conn_str, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                        (test_db_name,),
                    )
                    cur.execute(f"DROP DATABASE IF EXISTS {test_db_name}")

    def test_get_db_generator_lifecycle(self) -> None:
        db_gen = get_db()
        session = next(db_gen)
        self.assertIsInstance(session, Session)
        try:
            db_gen.throw(RuntimeError("Simulated error in request"))
        except RuntimeError:
            pass  # Expected to propagate after rollback


class IsolatedDatabaseTestCase(unittest.TestCase):
    """Base test class providing an isolated in-memory SQLite database per test."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestSessionLocal = sessionmaker(
            bind=cls.test_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    def setUp(self) -> None:
        Base.metadata.create_all(bind=self.test_engine)
        self.db = self.TestSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.test_engine)


class ModelMetadataAndSchemaTests(IsolatedDatabaseTestCase):
    """Test model metadata registration and table constraints."""

    def test_all_expected_tables_registered(self) -> None:
        expected_tables = {
            "users",
            "projects",
            "workspaces",
            "agent_runs",
            "execution_actions",
            "workspace_artifacts",
            "conversations",
            "messages",
            "memories",
            "documents",
            "document_chunks",
            "ingestion_jobs",
        }
        actual_tables = set(Base.metadata.tables.keys())
        self.assertTrue(expected_tables.issubset(actual_tables))


class RepositoryCrudAndConstraintTests(IsolatedDatabaseTestCase):
    """Test repository operations, constraints, and relationships."""

    def test_user_repository_crud(self) -> None:
        user = UserRepository.create(
            self.db, email="dev@example.com", name="Developer"
        )
        self.assertIsNotNone(user.id)
        self.assertEqual(user.email, "dev@example.com")

        fetched = UserRepository.get_by_email(self.db, "dev@example.com")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, user.id)

        # Unique email constraint
        with self.assertRaises(IntegrityError):
            UserRepository.create(self.db, email="dev@example.com")
        self.db.rollback()

    def test_project_and_workspace_lifecycle(self) -> None:
        user = UserRepository.create(self.db, email="alice@example.com", name="Alice")
        project, workspace = ProjectService.create_project(
            self.db, user_id=user.id, name="Test Project", description="Description"
        )
        self.assertEqual(project.user_id, user.id)
        self.assertEqual(workspace.project_id, project.id)
        self.assertEqual(workspace.user_id, user.id)

        # Test listing by user
        user_projects = ProjectService.list_user_projects(self.db, user_id=user.id)
        self.assertEqual(len(user_projects), 1)
        self.assertEqual(user_projects[0].id, project.id)

        # Test ownership verification
        verified_project = ProjectService.get_project_checked(
            self.db, project_id=project.id, user_id=user.id
        )
        self.assertEqual(verified_project.id, project.id)

        # Test ownership failure with different user
        bob = UserRepository.create(self.db, email="bob@example.com", name="Bob")
        with self.assertRaises(ProjectOwnershipError):
            ProjectService.get_project_checked(
                self.db, project_id=project.id, user_id=bob.id
            )

    def test_agent_run_and_actions_persistence(self) -> None:
        user = UserRepository.create(self.db, email="agent_user@example.com")
        project, workspace = ProjectService.create_project(
            self.db, user_id=user.id, name="Agent Run Project"
        )

        run = AgentRunService.start_run(
            db=self.db,
            workspace_id=workspace.id,
            project_id=project.id,
            user_id=user.id,
            objective="Analyze data and produce report",
            task_type="research",
            plan_json={"steps": ["search", "synthesize"]},
        )
        self.assertEqual(run.execution_status, "RUNNING")
        self.assertEqual(run.objective_status, "RUNNING")

        # Record action steps
        action1 = AgentRunService.record_action_step(
            db=self.db,
            run_id=run.id,
            step_id="step-1",
            tool_name="web_search",
            tool_args={"query": "PostgreSQL 16 release notes", "api_key": "secret_123"},
            tool_result={"count": 5, "items": ["item1", "item2"]},
            duration_ms=250,
            status="success",
        )
        self.assertEqual(action1.run_id, run.id)
        # Secret should be redacted
        self.assertEqual(action1.tool_args.get("api_key"), "[REDACTED_SECRET]")

        # Complete run
        completed_run = AgentRunService.complete_run(
            db=self.db,
            run_id=run.id,
            execution_status="SUCCESS",
            objective_status="SUCCESS",
            deliverable_status="SUCCESS",
            source_verification_status="SUCCESS",
            evidence_summary="5 verifiable sources extracted",
            final_summary="Analysis completed.",
        )
        self.assertEqual(completed_run.execution_status, "SUCCESS")
        self.assertIsNotNone(completed_run.completed_at)

        # Record artifact
        artifact = AgentRunService.register_artifact(
            db=self.db,
            workspace_id=workspace.id,
            file_path="report.md",
            file_size=1024,
            mime_type="text/markdown",
            run_id=run.id,
        )
        self.assertEqual(artifact.workspace_id, workspace.id)

        artifacts = WorkspaceArtifactRepository.list_by_run(self.db, run.id)
        self.assertEqual(len(artifacts), 1)

    def test_sensitive_data_redaction_and_truncation(self) -> None:
        data = {
            "query": "safe query",
            "api_key": "super_secret_groq_key",
            "groq_api_key": "another_secret",
            "bearer_token": "token_val",
            "nested": {
                "password": "mypassword",
                "normal": "value",
            },
            "huge_output": "A" * 60_000,
        }
        sanitized = _sanitize_data(data)
        self.assertEqual(sanitized["query"], "safe query")
        self.assertEqual(sanitized["api_key"], "[REDACTED_SECRET]")
        self.assertEqual(sanitized["groq_api_key"], "[REDACTED_SECRET]")
        self.assertEqual(sanitized["bearer_token"], "[REDACTED_SECRET]")
        self.assertEqual(sanitized["nested"]["password"], "[REDACTED_SECRET]")
        self.assertEqual(sanitized["nested"]["normal"], "value")
        self.assertTrue(sanitized["huge_output"].endswith("[truncated 10000 chars]"))

    def test_conversation_and_memory_crud(self) -> None:
        user = UserRepository.create(self.db, email="chat_user@example.com")
        convo = ConversationRepository.create(self.db, user_id=user.id, title="Test Chat")
        self.assertEqual(convo.title, "Test Chat")

        msg = ConversationRepository.add_message(
            self.db, conversation_id=convo.id, role="user", content="Hello Rorak"
        )
        self.assertEqual(msg.content, "Hello Rorak")

        messages = ConversationRepository.get_messages(self.db, convo.id)
        self.assertEqual(len(messages), 1)

        mem = MemoryRepository.create(
            self.db, user_id=user.id, content="User prefers Python", memory_type="preference"
        )
        memories = MemoryRepository.list_by_user(self.db, user.id)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].content, "User prefers Python")


class FastApiDatabaseEndpointTests(IsolatedDatabaseTestCase):
    """Test FastAPI /api/projects and /api/runs endpoints using test database."""

    def setUp(self) -> None:
        super().setUp()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    def test_create_and_list_projects_api(self) -> None:
        # Create project
        resp = self.client.post(
            "/api/projects",
            json={"name": "API Project Alpha", "description": "Created via API"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "API Project Alpha")
        project_id = data["id"]

        # List projects
        list_resp = self.client.get("/api/projects")
        self.assertEqual(list_resp.status_code, 200)
        projects = list_resp.json()
        self.assertGreaterEqual(len(projects), 1)
        self.assertTrue(any(p["id"] == project_id for p in projects))

        # Get project detail
        detail_resp = self.client.get(f"/api/projects/{project_id}")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.json()["id"], project_id)

    def test_runs_api(self) -> None:
        # Create a run record in DB
        user = UserRepository.get_or_create(self.db, email="default_agent_user@rorak.tech")
        proj, ws = ProjectService.create_project(self.db, user.id, "Runs Test Project")
        run = AgentRunService.start_run(
            self.db,
            workspace_id=ws.id,
            project_id=proj.id,
            user_id=user.id,
            objective="Test Run API",
            task_type="coding",
        )
        AgentRunService.record_action_step(
            self.db,
            run_id=run.id,
            step_id="step-1",
            tool_name="write_file",
            tool_args={"path": "main.py"},
            tool_result={"written": True},
            status="success",
        )

        # Test listing runs
        resp = self.client.get("/api/runs")
        self.assertEqual(resp.status_code, 200)
        runs = resp.json()
        self.assertGreaterEqual(len(runs), 1)

        # Test run detail
        detail_resp = self.client.get(f"/api/runs/{run.id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail = detail_resp.json()
        self.assertEqual(detail["id"], str(run.id))
        self.assertEqual(len(detail["execution_records"]), 1)
        self.assertEqual(detail["execution_records"][0]["tool_name"], "write_file")


if __name__ == "__main__":
    unittest.main()

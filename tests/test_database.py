"""Unit tests for the PostgreSQL / SQLAlchemy database layer and API endpoints."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent.api import app
from agent.database import get_db
from agent.models import (
    ApiKey,
    Base,
    ExecutionRecord,
    PromptTemplate,
    SavedPlan,
    User,
    WorkflowRun,
)

# In-memory SQLite engine for fast, isolated test execution
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.create_all(bind=test_engine)
        self.db = TestingSessionLocal()
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def test_user_creation_and_api_key_cascade(self) -> None:
        """Verify user model creation and cascade deletion of related API keys."""
        user = User(
            email="developer@example.com",
            name="Alice",
            tier="pro",
        )
        self.db.add(user)
        self.db.commit()

        api_key = ApiKey(
            user_id=user.id,
            provider="groq",
            encrypted_key="gsk_test_secret_encrypted_value",
            is_active=True,
        )
        self.db.add(api_key)
        self.db.commit()

        # Query user with relationship
        fetched_user = self.db.query(User).filter(User.email == "developer@example.com").first()
        self.assertIsNotNone(fetched_user)
        self.assertEqual(len(fetched_user.api_keys), 1)
        self.assertEqual(fetched_user.api_keys[0].provider, "groq")

        # Cascade delete test
        self.db.delete(fetched_user)
        self.db.commit()

        remaining_keys = self.db.query(ApiKey).filter(ApiKey.user_id == user.id).all()
        self.assertEqual(len(remaining_keys), 0)

    def test_workflow_run_saved_plan_and_records(self) -> None:
        """Verify workflow runs can store complex plans and multiple tool execution records."""
        run_id = str(uuid4())
        run = WorkflowRun(
            id=run_id,
            user_prompt="Build a fullstack portfolio app",
            status="DONE",
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            duration_ms=4500,
        )
        self.db.add(run)

        # Plan with JSON features and task steps
        plan = SavedPlan(
            run_id=run_id,
            app_name="Portfolio App",
            description="Personal developer portfolio site",
            techstack="React, FastAPI, PostgreSQL",
            features=["Dark Mode", "Project Gallery", "Contact Form"],
            task_steps=[
                {"file_path": "main.py", "task_description": "Setup entrypoint"},
                {"file_path": "models.py", "task_description": "Define models"},
            ],
        )
        self.db.add(plan)

        # Tool audit record
        record = ExecutionRecord(
            run_id=run_id,
            step_id="step-1",
            tool_name="write_file",
            tool_args={"path": "main.py", "content": "print('hello')"},
            tool_result="File written successfully",
            duration_ms=120,
            status="success",
        )
        self.db.add(record)
        self.db.commit()

        # Parameterized query lookup
        fetched_run = self.db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        self.assertIsNotNone(fetched_run)
        self.assertEqual(fetched_run.status, "DONE")
        self.assertIsNotNone(fetched_run.plan)
        self.assertEqual(fetched_run.plan.app_name, "Portfolio App")
        self.assertEqual(len(fetched_run.plan.features), 3)
        self.assertEqual(len(fetched_run.execution_records), 1)
        self.assertEqual(fetched_run.execution_records[0].tool_name, "write_file")

    def test_runs_api_endpoints(self) -> None:
        """Verify GET /v1/runs and GET /v1/runs/{run_id} endpoints return proper data."""
        run_id = str(uuid4())
        run = WorkflowRun(
            id=run_id,
            user_prompt="Generate a REST API with tests",
            status="DONE",
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            duration_ms=2100,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(run)

        plan = SavedPlan(
            run_id=run_id,
            app_name="REST API Service",
            description="Minimal REST service",
            techstack="FastAPI",
            features=["Healthcheck", "CRUD endpoints"],
        )
        self.db.add(plan)
        self.db.commit()

        # 1. Test listing runs
        res_list = self.client.get("/v1/runs")
        self.assertEqual(res_list.status_code, 200)
        items = res_list.json()
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["id"], run_id)
        self.assertEqual(items[0]["user_prompt"], "Generate a REST API with tests")

        # 2. Test run detail endpoint
        res_detail = self.client.get(f"/v1/runs/{run_id}")
        self.assertEqual(res_detail.status_code, 200)
        detail = res_detail.json()
        self.assertEqual(detail["id"], run_id)
        self.assertIsNotNone(detail["plan"])
        self.assertEqual(detail["plan"]["app_name"], "REST API Service")

        # 3. Test 404 for unknown run_id
        res_404 = self.client.get(f"/v1/runs/{uuid4()}")
        self.assertEqual(res_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()

"""Safe, repeatable data migration script from SQLite to PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_postgres.py --sqlite-path rorak_dev.db
    python scripts/migrate_sqlite_to_postgres.py --sqlite-path "E:/Coding/Hackathons/JU-Techfest 26/rorak_dev.db" --dry-run
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import sys
from typing import Any
from uuid import UUID

# Ensure repo root is on sys.path
BASE_ROOT = Path(__file__).resolve().parent.parent
if str(BASE_ROOT) not in sys.path:
    sys.path.insert(0, str(BASE_ROOT))

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agent.db.config import DATABASE_URL, normalize_database_url
from agent.db.database import build_engine
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_migration")


def parse_uuid(val: Any) -> UUID | None:
    if val is None:
        return None
    if isinstance(val, UUID):
        return val
    s = str(val).strip()
    try:
        return UUID(s)
    except ValueError:
        if s.isdigit():
            return UUID(f"00000000-0000-0000-0000-{int(s):012d}")
        try:
            return UUID(hex=s)
        except Exception:
            return None


def parse_timestamp(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return datetime.now(timezone.utc)


def parse_json(val: Any) -> Any:
    if not val:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(str(val))
    except Exception:
        return str(val)


def migrate_data(sqlite_path: str, pg_url: str, dry_run: bool = False) -> None:
    logger.info("Connecting to source SQLite: %s", sqlite_path)
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    logger.info("Connecting to target database: %s", pg_url)
    engine = build_engine(pg_url)

    # Validate target schema exists
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1 FROM users LIMIT 1"))
        logger.info("Target schema verified (users table accessible).")

    stats = {
        "users": 0,
        "conversations": 0,
        "messages": 0,
        "memories": 0,
        "projects": 0,
        "workspaces": 0,
        "agent_runs": 0,
        "execution_actions": 0,
        "workspace_artifacts": 0,
    }

    with Session(engine) as session:
        try:
            # 1. Users
            users_rows = sqlite_cur.execute("SELECT * FROM users").fetchall()
            for r in users_rows:
                u_id = parse_uuid(r["id"])
                if not session.get(User, u_id):
                    session.add(
                        User(
                            id=u_id,
                            email=r["email"],
                            name=r["name"] if "name" in r.keys() else None,
                            password_hash=r["password_hash"] if "password_hash" in r.keys() else None,
                            created_at=parse_timestamp(r["created_at"]) or datetime.now(timezone.utc),
                            updated_at=parse_timestamp(r["updated_at"]) or datetime.now(timezone.utc),
                        )
                    )
                    stats["users"] += 1
            session.flush()

            # 2. Conversations
            if "conversations" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                convo_rows = sqlite_cur.execute("SELECT * FROM conversations").fetchall()
                for r in convo_rows:
                    c_id = parse_uuid(r["id"])
                    if not session.get(Conversation, c_id):
                        session.add(
                            Conversation(
                                id=c_id,
                                user_id=parse_uuid(r["user_id"]),
                                title=r["title"],
                                created_at=parse_timestamp(r["created_at"]) or datetime.now(timezone.utc),
                                updated_at=parse_timestamp(r["updated_at"]) or datetime.now(timezone.utc),
                            )
                        )
                        stats["conversations"] += 1
                session.flush()

            # 3. Messages
            if "messages" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                msg_rows = sqlite_cur.execute("SELECT * FROM messages").fetchall()
                for r in msg_rows:
                    m_id = parse_uuid(r["id"])
                    if not session.get(Message, m_id):
                        session.add(
                            Message(
                                id=m_id,
                                conversation_id=parse_uuid(r["conversation_id"]),
                                role=r["role"],
                                content=r["content"],
                                created_at=parse_timestamp(r["created_at"]) or datetime.now(timezone.utc),
                            )
                        )
                        stats["messages"] += 1
                session.flush()

            # 4. Memories
            if "memories" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                mem_rows = sqlite_cur.execute("SELECT * FROM memories").fetchall()
                for r in mem_rows:
                    mem_id = parse_uuid(r["id"])
                    if not session.get(Memory, mem_id):
                        session.add(
                            Memory(
                                id=mem_id,
                                user_id=parse_uuid(r["user_id"]),
                                content=r["content"],
                                memory_type=r["memory_type"],
                                created_at=parse_timestamp(r["created_at"]) or datetime.now(timezone.utc),
                                updated_at=parse_timestamp(r["updated_at"]) or datetime.now(timezone.utc),
                            )
                        )
                        stats["memories"] += 1
                session.flush()

            # 5. Projects
            if "projects" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                proj_rows = sqlite_cur.execute("SELECT * FROM projects").fetchall()
                for r in proj_rows:
                    p_id = parse_uuid(r["id"])
                    u_id = parse_uuid(r["user_id"])
                    if not p_id or not u_id:
                        continue
                    if not session.get(User, u_id):
                        logger.warning("Skipping project %s: owner user %s not found", p_id, u_id)
                        continue
                    if not session.get(Project, p_id):
                        session.add(
                            Project(
                                id=p_id,
                                user_id=u_id,
                                name=r["name"],
                                description=r["description"],
                                status=r["status"] if "status" in r.keys() else "active",
                                created_at=parse_timestamp(r["created_at"]) or datetime.now(timezone.utc),
                                updated_at=parse_timestamp(r["updated_at"]) or datetime.now(timezone.utc),
                            )
                        )
                        stats["projects"] += 1
                session.flush()

            # 6. Workspaces
            if "workspaces" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                ws_rows = sqlite_cur.execute("SELECT * FROM workspaces").fetchall()
                for r in ws_rows:
                    w_id = parse_uuid(r["id"])
                    if "project_id" in r.keys() and r["project_id"]:
                        p_id = parse_uuid(r["project_id"])
                    else:
                        continue
                    u_id = parse_uuid(r["user_id"])
                    if not w_id or not p_id or not u_id:
                        continue
                    if not session.get(Project, p_id) or not session.get(User, u_id):
                        logger.warning("Skipping workspace %s: project %s or user %s missing", w_id, p_id, u_id)
                        continue
                    if not session.get(Workspace, w_id):
                        session.add(
                            Workspace(
                                id=w_id,
                                project_id=p_id,
                                user_id=u_id,
                                storage_path=r["storage_path"],
                                status=r["status"] if "status" in r.keys() else "ready",
                                created_at=parse_timestamp(r["created_at"]) or datetime.now(timezone.utc),
                                updated_at=parse_timestamp(r["updated_at"]) or datetime.now(timezone.utc),
                            )
                        )
                        stats["workspaces"] += 1
                session.flush()

            # 7. Agent Runs
            if "agent_runs" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                run_rows = sqlite_cur.execute("SELECT * FROM agent_runs").fetchall()
                for r in run_rows:
                    run_id = parse_uuid(r["id"])
                    ws_id = parse_uuid(r["workspace_id"])
                    p_id = parse_uuid(r["project_id"])
                    u_id = parse_uuid(r["user_id"])
                    if not run_id or not ws_id or not p_id or not u_id:
                        continue
                    if not session.get(Workspace, ws_id) or not session.get(Project, p_id) or not session.get(User, u_id):
                        logger.warning("Skipping run %s: workspace, project, or user FK missing", run_id)
                        continue
                    if not session.get(AgentRun, run_id):
                        session.add(
                            AgentRun(
                                id=run_id,
                                workspace_id=ws_id,
                                project_id=p_id,
                                user_id=u_id,
                                objective=r["objective"],
                                task_type=r["task_type"] if "task_type" in r.keys() else "general",
                                plan_json=parse_json(r["plan_json"]) if "plan_json" in r.keys() else None,
                                execution_status=r["execution_status"],
                                deliverable_status=r["deliverable_status"] if "deliverable_status" in r.keys() else None,
                                source_verification_status=r["source_verification_status"] if "source_verification_status" in r.keys() else None,
                                objective_status=r["objective_status"],
                                evidence_summary=r["evidence_summary"] if "evidence_summary" in r.keys() else None,
                                final_summary=r["final_summary"] if "final_summary" in r.keys() else None,
                                error_message=r["error_message"] if "error_message" in r.keys() else None,
                                started_at=parse_timestamp(r["started_at"]) or datetime.now(timezone.utc),
                                completed_at=parse_timestamp(r["completed_at"]),
                            )
                        )
                        stats["agent_runs"] += 1
                session.flush()

            # 8. Execution Actions
            if "execution_actions" in [t[0] for t in sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]:
                act_rows = sqlite_cur.execute("SELECT * FROM execution_actions").fetchall()
                for r in act_rows:
                    act_id = parse_uuid(r["id"])
                    run_id = parse_uuid(r["run_id"])
                    if not act_id or not run_id or not session.get(AgentRun, run_id):
                        continue
                    if not session.get(ExecutionAction, act_id):
                        session.add(
                            ExecutionAction(
                                id=act_id,
                                run_id=run_id,
                                step_id=r["step_id"],
                                tool_name=r["tool_name"],
                                tool_args=parse_json(r["tool_args"]) if "tool_args" in r.keys() else None,
                                tool_result=parse_json(r["tool_result"]) if "tool_result" in r.keys() else None,
                                status=r["status"],
                                duration_ms=r["duration_ms"] if "duration_ms" in r.keys() else 0,
                                retry_count=r["retry_count"] if "retry_count" in r.keys() else 0,
                                error_details=r["error_details"] if "error_details" in r.keys() else None,
                                started_at=parse_timestamp(r["started_at"]) or datetime.now(timezone.utc),
                                completed_at=parse_timestamp(r["completed_at"]),
                            )
                        )
                        stats["execution_actions"] += 1
                session.flush()

            if dry_run:
                logger.info("[DRY RUN] Rolled back changes. Statistics of records that would be inserted:")
                session.rollback()
            else:
                session.commit()
                logger.info("Migration successfully committed! Statistics:")

            for table, count in stats.items():
                logger.info("  %s: %d new records imported", table, count)

        except Exception as e:
            session.rollback()
            logger.error("Migration failed, transaction rolled back safely: %s", e)
            raise
        finally:
            sqlite_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL.")
    parser.add_argument("--sqlite-path", default="rorak_dev.db", help="Path to source SQLite file")
    parser.add_argument("--pg-url", default=DATABASE_URL, help="Target PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without committing")
    args = parser.parse_args()

    migrate_data(args.sqlite_path, args.pg_url, dry_run=args.dry_run)

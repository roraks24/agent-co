"""Agent Workspace REST and SSE streaming routes for Rorak AI."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from agent.source_serializer import clean_transport_escapes
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.agent.graph import astream_workflow, get_graph_schema
from backend.agent.llm import build_chat_model
from backend.agent.prompts import get_prompt_schema
from backend.agent.tools_registry import GLOBAL_TOOL_REGISTRY
from backend.agent.workspace_service import (
    WorkspaceValidationError,
    create_zip_archive,
    delete_file,
    get_workspace_dir,
    list_relative_files,
    list_tree,
    read_text_file,
    resolve_safe_path,
    workspace_context,
    write_text_file,
)
from backend.core.auth import get_current_user, get_optional_current_user
from backend.core.database import SessionLocal, get_db
from backend.core.security import decode_access_token
from backend.services.agent_workspace_service import AgentWorkspaceService
from backend.models.db import (
    AgentRun,
    ExecutionAction,
    Project,
    User,
    Workspace,
    WorkspaceArtifact,
)

logger = logging.getLogger("rorak.agent.routes")

router = APIRouter(prefix="/api/agent", tags=["agent-workspace"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class StartRunRequest(BaseModel):
    objective: str = Field(..., min_length=1)
    task_type: Optional[str] = "general"
    model: Optional[str] = None
    recursion_limit: int = 50
    mutable_prompt: Optional[str] = None
    prompt_overrides: Optional[dict[str, str]] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    custom_keys: Optional[dict[str, Any]] = None


class WriteFileRequest(BaseModel):
    path: str
    content: str


class CreateFileRequest(BaseModel):
    path: str
    content: Optional[str] = None
    is_directory: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers & Ownership Guards
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_user_id(current_user: Optional[User], db: Optional[Session] = None) -> UUID:
    """Return user id or ensure a fallback default demo user in database."""
    if current_user and current_user.id:
        return current_user.id if isinstance(current_user.id, UUID) else UUID(str(current_user.id))
    guest_uuid = UUID("a0000000-0000-4000-8000-000000000001")
    if db is not None:
        try:
            guest_user = db.query(User).filter(User.id == guest_uuid).first()
            if not guest_user:
                guest_user = User(
                    id=guest_uuid,
                    email="guest@rorak.local",
                    name="Guest User",
                )
                db.add(guest_user)
                db.flush()
        except Exception:
            db.rollback()
    return guest_uuid


def _get_project_with_ownership(
    project_id: UUID,
    db: Session,
    current_user: Optional[User],
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if current_user and project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access to this project is forbidden.")
    return project


def _get_workspace_with_ownership(
    workspace_id: UUID | str,
    db: Session,
    current_user: Optional[User],
) -> Workspace:
    ws_uuid = None
    if isinstance(workspace_id, UUID):
        ws_uuid = workspace_id
    else:
        try:
            ws_uuid = UUID(str(workspace_id))
        except (ValueError, AttributeError):
            ws_uuid = None

    workspace = None
    if ws_uuid:
        workspace = db.query(Workspace).filter(Workspace.id == ws_uuid).first()

    if not workspace:
        # Check if directory exists on disk for default/demo workspace
        ws_path = get_workspace_dir(str(workspace_id))
        if ws_path.exists():
            # Create transient DB record if missing
            user_id = _resolve_user_id(current_user, db)
            dummy_proj = Project(
                name="Agent Workspace",
                description="Auto-created workspace project",
                user_id=user_id,
            )
            db.add(dummy_proj)
            db.flush()
            workspace = Workspace(
                id=ws_uuid or uuid4(),
                project_id=dummy_proj.id,
                user_id=user_id,
                storage_path=str(ws_path),
            )
            db.add(workspace)
            db.commit()
            return workspace
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if current_user and workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access to this workspace is forbidden.")
    return workspace


# ─────────────────────────────────────────────────────────────────────────────
# 1. Projects Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    req: CreateProjectRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Create a new project and initialize its dedicated persistent cloud workspace."""
    user_id = _resolve_user_id(current_user, db)
    proj_id = uuid4()
    proj = Project(
        id=proj_id,
        name=req.name.strip(),
        description=req.description,
        user_id=user_id,
    )
    db.add(proj)

    ws_id = uuid4()
    ws_path = str(get_workspace_dir(str(ws_id)))
    workspace = Workspace(
        id=ws_id,
        project_id=proj_id,
        user_id=user_id,
        storage_path=ws_path,
        status="ready",
    )
    db.add(workspace)
    db.commit()

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(proj_id),
        "name": req.name.strip(),
        "description": req.description,
        "status": "active",
        "workspace_id": str(ws_id),
        "created_at": now_iso,
        "updated_at": now_iso,
    }


@router.get("/projects")
def list_projects(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """List projects owned by the user (or all demo projects if unauthenticated)."""
    user_id = _resolve_user_id(current_user, db)
    query = db.query(Project)
    if current_user:
        query = query.filter(Project.user_id == user_id)
    projects = query.order_by(Project.updated_at.desc()).limit(50).all()

    results = []
    for p in projects:
        ws = db.query(Workspace).filter(Workspace.project_id == p.id).first()
        results.append({
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "workspace_id": str(ws.id) if ws else None,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        })
    return {"projects": results}


@router.get("/projects/{project_id}")
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Retrieve project details, workspace ID, and recent runs."""
    project = _get_project_with_ownership(project_id, db, current_user)
    workspace = db.query(Workspace).filter(Workspace.project_id == project.id).first()

    recent_runs = (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project.id)
        .order_by(AgentRun.started_at.desc())
        .limit(10)
        .all()
    )

    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "workspace_id": str(workspace.id) if workspace else None,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "recent_runs": [
            {
                "id": str(r.id),
                "objective": r.objective,
                "task_type": r.task_type,
                "objective_status": r.objective_status,
                "execution_status": r.execution_status,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in recent_runs
        ],
    }


@router.delete("/projects/{project_id}")
def delete_project_endpoint(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Delete a project and its workspace storage."""
    project = _get_project_with_ownership(project_id, db, current_user)
    workspace = db.query(Workspace).filter(Workspace.project_id == project.id).first()
    if workspace:
        # Clean filesystem
        ws_dir = get_workspace_dir(str(workspace.id))
        import shutil
        if ws_dir.exists():
            shutil.rmtree(ws_dir, ignore_errors=True)
    db.delete(project)
    db.commit()
    return {"status": "deleted", "project_id": str(project_id)}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Workspace File Operations
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/tree")
def get_workspace_tree(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Return interactive directory tree of workspace files."""
    _get_workspace_with_ownership(workspace_id, db, current_user)
    tree = list_tree(str(workspace_id))
    return {"workspace_id": str(workspace_id), "tree": tree}


@router.get("/workspaces/{workspace_id}/files")
def read_workspace_file(
    workspace_id: UUID,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Read a text file from the workspace filesystem."""
    _get_workspace_with_ownership(workspace_id, db, current_user)
    try:
        content = read_text_file(path, str(workspace_id))
        return {
            "path": path,
            "content": content,
            "size": len(content),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File '{path}' not found in workspace.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/workspaces/{workspace_id}/files")
def save_workspace_file(
    workspace_id: UUID,
    req: WriteFileRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Save updated text content to a file in the workspace."""
    _get_workspace_with_ownership(workspace_id, db, current_user)
    try:
        rel = write_text_file(req.path, req.content, str(workspace_id))
        return {
            "path": rel,
            "size": len(req.content),
            "status": "saved",
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/workspaces/{workspace_id}/files")
def create_workspace_item(
    workspace_id: UUID,
    req: CreateFileRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Create a new file or directory inside the workspace."""
    _get_workspace_with_ownership(workspace_id, db, current_user)
    try:
        target = resolve_safe_path(req.path, str(workspace_id))
        if req.is_directory:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            initial_content = req.content if req.content is not None else ""
            target.write_text(initial_content, encoding="utf-8")
        return {"path": req.path, "status": "created"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/workspaces/{workspace_id}/files")
def delete_workspace_file(
    workspace_id: UUID,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Delete a file or folder from the workspace."""
    _get_workspace_with_ownership(workspace_id, db, current_user)
    success = delete_file(path, str(workspace_id))
    if not success:
        raise HTTPException(status_code=404, detail=f"File '{path}' not found.")
    return {"path": path, "status": "deleted"}


@router.get("/workspaces/{workspace_id}/download")
@router.get("/workspaces/{workspace_id}/zip")
def download_workspace_zip(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Generate and download a clean ZIP archive of the persistent workspace."""
    ws = _get_workspace_with_ownership(workspace_id, db, current_user)
    project = db.query(Project).filter(Project.id == ws.project_id).first()
    proj_name = re.sub(r"[^A-Za-z0-9_-]", "_", project.name if project else "workspace")

    zip_bytes = create_zip_archive(str(workspace_id))
    filename = f"{proj_name}_{str(workspace_id)[:8]}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2.1 Workspace Live Preview Endpoint
# ─────────────────────────────────────────────────────────────────────────────

PREVIEW_MIME_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def _get_preview_mime_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in PREVIEW_MIME_TYPES:
        return PREVIEW_MIME_TYPES[ext]
    guessed, _ = mimetypes.guess_type(file_path.name)
    return guessed or "application/octet-stream"


@router.get("/workspaces/{workspace_id}/preview")
@router.get("/workspaces/{workspace_id}/preview/{subpath:path}")
def preview_workspace_file(
    workspace_id: str,
    subpath: str = "",
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Securely serve static web preview files and assets directly from workspace storage.
    Enforces project ownership, strict path traversal checks, and correct MIME types.
    """
    # 1. Resolve authentication either from Bearer header or query token parameter
    resolved_user = current_user
    if not resolved_user and token:
        try:
            payload = decode_access_token(token)
            user_id_str = payload.get("sub")
            if user_id_str:
                resolved_user = db.query(User).filter(User.id == UUID(str(user_id_str))).first()
        except Exception as exc:
            logger.debug("Preview token verification error: %s", exc)

    # 2. Enforce workspace ownership
    _get_workspace_with_ownership(workspace_id, db, resolved_user)

    # 3. Clean and resolve safe subpath
    clean_subpath = subpath.strip().replace("\\", "/").lstrip("/")
    if not clean_subpath:
        clean_subpath = "index.html"

    try:
        target = resolve_safe_path(clean_subpath, str(workspace_id))
    except WorkspaceValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Path traversal forbidden: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # 4. If directory was requested, look for index.html inside it
    if target.is_dir():
        candidate_index = target / "index.html"
        if candidate_index.is_file():
            target = candidate_index
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Directory index not found for path '{clean_subpath}'",
            )

    # 5. Handle missing file
    if not target.exists():
        if clean_subpath.lower() in ("index.html", "index.htm"):
            empty_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Workspace Live Preview</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #09090b;
      color: #94a3b8;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      padding: 20px;
      box-sizing: border-box;
    }
    .preview-card {
      text-align: center;
      max-width: 460px;
      padding: 36px 28px;
      background: #141416;
      border: 1px solid #27272a;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
    }
    .icon { font-size: 40px; margin-bottom: 12px; }
    h2 { color: #f8fafc; font-size: 19px; margin: 0 0 8px; font-weight: 600; }
    p { font-size: 14px; line-height: 1.6; margin: 0 0 18px; color: #a1a1aa; }
    .badge {
      display: inline-block;
      padding: 4px 12px;
      background: #1e293b;
      color: #60a5fa;
      border: 1px solid #334155;
      border-radius: 9999px;
      font-size: 12px;
      font-family: ui-monospace, monospace;
    }
  </style>
</head>
<body>
  <div class="preview-card">
    <div class="icon">🌐</div>
    <h2>Live Preview Ready</h2>
    <p>No <code>index.html</code> was found in this workspace yet. Execute a software generation objective (e.g., portfolio or web app) to see live interactive output here.</p>
    <span class="badge">Awaiting index.html</span>
  </div>
</body>
</html>"""
            return Response(
                content=empty_html,
                status_code=status.HTTP_200_OK,
                media_type="text/html",
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{clean_subpath}' not found in workspace.",
        )

    # 6. Stream asset with correct MIME type, live unescaping, and secure sandbox headers
    mime_type = _get_preview_mime_type(target)
    headers = {
        "Content-Type": mime_type,
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Security-Policy": "frame-ancestors *; default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https:;",
        "X-Content-Type-Options": "nosniff",
    }

    ext = target.suffix.lower()
    if ext in (".html", ".htm"):
        raw_text = target.read_text(encoding="utf-8", errors="replace")
        cleaned_html = clean_transport_escapes(raw_text, clean_subpath)
        # Inject <base> tag so relative CSS, JS, and image paths always resolve within this workspace preview
        if "<base " not in cleaned_html.lower() and re.search(r"<head[^>]*>", cleaned_html, re.IGNORECASE):
            base_tag = f'<base href="/api/agent/workspaces/{workspace_id}/preview/">'
            cleaned_html = re.sub(r"(<head[^>]*>)", r"\1\n  " + base_tag, cleaned_html, count=1, flags=re.IGNORECASE)
        return Response(content=cleaned_html, media_type="text/html; charset=utf-8", headers=headers)

    if ext == ".css":
        raw_text = target.read_text(encoding="utf-8", errors="replace")
        cleaned_css = clean_transport_escapes(raw_text, clean_subpath)
        return Response(content=cleaned_css, media_type="text/css; charset=utf-8", headers=headers)

    if ext in (".js", ".mjs"):
        raw_text = target.read_text(encoding="utf-8", errors="replace")
        cleaned_js = clean_transport_escapes(raw_text, clean_subpath)
        return Response(content=cleaned_js, media_type="application/javascript; charset=utf-8", headers=headers)

    return FileResponse(path=str(target), media_type=mime_type, headers=headers)



# ─────────────────────────────────────────────────────────────────────────────
# 3. Agent Runs & SSE Streaming
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/runs")
async def start_workspace_agent_run(
    workspace_id: UUID,
    req: StartRunRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Start an agent run on this workspace and stream SSE lifecycle & tool events."""
    workspace = _get_workspace_with_ownership(workspace_id, db, current_user)
    user_id = _resolve_user_id(current_user, db)

    # Initialize LLM with optional user custom keys & provider settings
    try:
        llm = build_chat_model(
            model=req.model,
            api_key=req.api_key,
            provider=req.provider,
            base_url=req.base_url,
            custom_keys=req.custom_keys,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Create AgentRun record
    run_id = uuid4()
    agent_run = AgentRun(
        id=run_id,
        workspace_id=workspace.id,
        project_id=workspace.project_id,
        user_id=user_id,
        objective=req.objective.strip(),
        task_type=req.task_type or "general",
        execution_status="RUNNING",
        objective_status="RUNNING",
    )
    db.add(agent_run)
    db.commit()

    async def sse_event_stream() -> AsyncIterator[str]:
        event_id = 0
        run_start = perf_counter()

        def _format_sse(evt_name: str, payload: dict[str, Any]) -> str:
            nonlocal event_id
            event_id += 1
            payload["event_id"] = event_id
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload["run_id"] = str(run_id)
            payload["workspace_id"] = str(workspace_id)
            data_str = json.dumps(payload, default=str)
            return f"event: {evt_name}\r\ndata: {data_str}\r\n\r\n"

        yield _format_sse(
            "run_started",
            {
                "node": None,
                "state": "active",
                "activity_score": 0.1,
                "message": f"Agent run initialized for objective: {req.objective[:80]}...",
            },
        )

        latest_obj_status = "PENDING"
        latest_final_summary = None
        latest_verification = None

        with workspace_context(str(workspace_id)):
            try:
                async for chunk in astream_workflow(
                    user_prompt=req.objective,
                    llm=llm,
                    recursion_limit=req.recursion_limit,
                    mutable_prompt=req.mutable_prompt,
                    prompt_overrides=req.prompt_overrides,
                    workspace_id=str(workspace_id),
                ):
                    # Unpack LangGraph chunk (namespace, mode, data)
                    if isinstance(chunk, tuple):
                        if len(chunk) == 3:
                            ns, mode, data = chunk
                        elif len(chunk) == 2:
                            mode, data = chunk
                            ns = None
                        else:
                            continue
                    else:
                        continue

                    if mode == "debug" and isinstance(data, dict):
                        if data.get("type") == "task":
                            payload = data.get("payload") or {}
                            task_name = payload.get("name")
                            if task_name in {"planner", "architect", "coder"}:
                                yield _format_sse(
                                    "on_node_start",
                                    {
                                        "node": task_name,
                                        "state": "running",
                                        "message": f"Executing node: {task_name}",
                                    },
                                )

                    if mode == "updates" and isinstance(data, dict):
                        for node_name, update in data.items():
                            node = str(node_name)
                            if not isinstance(update, dict):
                                continue

                            # 1. Action plan established (only once from planner node)
                            if node == "planner" and "goal_plan" in update and update["goal_plan"]:
                                gp = update["goal_plan"]
                                gp_dict = gp.model_dump() if hasattr(gp, "model_dump") else gp
                                yield _format_sse(
                                    "on_action_plan",
                                    {
                                        "node": node,
                                        "plan": gp_dict,
                                        "task_type": gp_dict.get("task_type", "general"),
                                        "message": f"Plan created: {len(gp_dict.get('steps', []))} steps planned.",
                                    },
                                )

                            # 2. Tool execution finished
                            if "current_execution" in update and update["current_execution"]:
                                er = update["current_execution"]
                                t_name = er.get("tool_name", "tool")
                                t_status = er.get("status", "success")
                                t_dur = er.get("duration_ms", 0)

                                # Persist execution action in database
                                try:
                                    with SessionLocal() as db_session:
                                        action_svc = AgentWorkspaceService(db_session)
                                        action_svc.record_action(
                                            run_id=run_id,
                                            step_id=str(er.get("step_id", "step-unknown")),
                                            tool_name=str(t_name),
                                            tool_args=er.get("tool_args"),
                                            tool_result=er.get("tool_result"),
                                            status=str(t_status),
                                            duration_ms=int(t_dur),
                                            retry_count=int(er.get("retry_count", 0)),
                                            error_details=er.get("error"),
                                        )
                                except Exception as db_err:
                                    logger.warning("Could not persist tool action: %s", db_err)

                                yield _format_sse(
                                    "on_tool_end",
                                    {
                                        "node": node,
                                        "tool_name": t_name,
                                        "step_id": er.get("step_id"),
                                        "status": t_status,
                                        "duration_ms": t_dur,
                                        "execution_record": er,
                                        "message": f"Tool '{t_name}' finished ({t_dur}ms) [{t_status}].",
                                    },
                                )

                            # 3. Node completion update
                            yield _format_sse(
                                "on_node_end",
                                {
                                    "node": node,
                                    "state": "completed",
                                    "activity_score": 0.5,
                                    "message": f"Node '{node}' completed.",
                                },
                            )

                            # 4. Final verification
                            if "verification" in update and update["verification"]:
                                vf = update["verification"]
                                vf_dict = vf.model_dump() if hasattr(vf, "model_dump") else vf
                                latest_obj_status = update.get("objective_status", "SUCCESS")
                                latest_final_summary = update.get("final_summary")
                                latest_verification = vf_dict

                                yield _format_sse(
                                    "on_verification",
                                    {
                                        "node": node,
                                        "objective_status": latest_obj_status,
                                        "verification": vf_dict,
                                        "final_summary": latest_final_summary,
                                        "message": f"Verification complete: status is {latest_obj_status}.",
                                    },
                                )

                # Run completed
                dur_ms = int((perf_counter() - run_start) * 1000)
                msg = (
                    "Workflow finished successfully."
                    if latest_obj_status == "SUCCESS"
                    else f"Workflow completed: objective {latest_obj_status}."
                )

                # Persist completed run status in PostgreSQL
                try:
                    with SessionLocal() as db_session:
                        run_svc = AgentWorkspaceService(db_session)
                        run_svc.update_agent_run_completion(
                            run_id=run_id,
                            execution_status="COMPLETED",
                            deliverable_status=latest_verification.get("deliverable_status") if latest_verification else None,
                            source_verification_status=latest_verification.get("source_verification_status") if latest_verification else None,
                            objective_status=latest_obj_status,
                            evidence_summary=latest_verification.get("evidence_summary") if latest_verification else None,
                            final_summary=latest_final_summary,
                        )
                except Exception as db_err:
                    logger.warning("Could not persist agent run completion: %s", db_err)

                yield _format_sse(
                    "run_complete",
                    {
                        "node": None,
                        "state": "completed",
                        "objective_status": latest_obj_status,
                        "verification": latest_verification,
                        "final_summary": latest_final_summary,
                        "duration_ms": dur_ms,
                        "message": msg,
                    },
                )

            except Exception as exc:
                logger.exception("Agent run failed: %s", exc)

                try:
                    with SessionLocal() as db_session:
                        run_svc = AgentWorkspaceService(db_session)
                        run_svc.update_agent_run_completion(
                            run_id=run_id,
                            execution_status="FAILED",
                            objective_status="FAILED",
                            error_message=str(exc),
                        )
                except Exception as db_err:
                    logger.warning("Could not persist failed agent run: %s", db_err)

                yield _format_sse(
                    "error",
                    {
                        "node": None,
                        "error_type": "execution_error",
                        "message": str(exc),
                    },
                )

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/workspaces/{workspace_id}/runs")
def list_workspace_runs(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """List execution history and past runs for this workspace."""
    _get_workspace_with_ownership(workspace_id, db, current_user)
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.workspace_id == workspace_id)
        .order_by(AgentRun.started_at.desc())
        .limit(30)
        .all()
    )
    return {
        "runs": [
            {
                "id": str(r.id),
                "objective": r.objective,
                "task_type": r.task_type,
                "objective_status": r.objective_status,
                "execution_status": r.execution_status,
                "evidence_summary": r.evidence_summary,
                "final_summary": r.final_summary,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tools & Prompts Schema Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tools")
def list_registered_tools():
    """Return all available tools with input/output schemas."""
    return {"tools": GLOBAL_TOOL_REGISTRY.list_tools()}


@router.get("/prompts")
def get_prompts_info():
    """Return node prompt configuration schema."""
    return get_prompt_schema()


@router.get("/graph/schema")
def get_graph_schema_info():
    """Return workflow graph node and edge schema."""
    return get_graph_schema()

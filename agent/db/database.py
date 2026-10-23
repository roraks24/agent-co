"""SQLite database manager and repository for API Providers."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent.adaptive.models import (
    ApiRegistryEntry,
    CostTier,
    LatencyTier,
    Modality,
    TaskTier,
)
from agent.db.crypto import decrypt_secret, encrypt_secret
from agent.db.models import (
    ApiProviderCreate,
    ApiProviderRecord,
    ApiProviderUpdate,
)

DEFAULT_DB_FILE = "data/agent_co.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> str:
    """Return database path from environment or default file."""
    custom_path = os.getenv("DATABASE_PATH")
    if custom_path:
        return custom_path
    db_file = os.path.abspath(DEFAULT_DB_FILE)
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    return db_file


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Create a SQLite connection with Row factory enabled."""
    path = db_path or get_db_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize SQLite schema and seed default records if table is empty."""
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_providers (
                id TEXT PRIMARY KEY,
                provider_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                api_key_encrypted TEXT NOT NULL DEFAULT '',
                base_url TEXT,
                model_name TEXT NOT NULL,
                capability_tier TEXT NOT NULL DEFAULT 'MEDIUM',
                supported_tasks TEXT NOT NULL DEFAULT '["text", "code"]',
                context_window INTEGER NOT NULL DEFAULT 8192,
                max_output_tokens INTEGER NOT NULL DEFAULT 4096,
                latency_tier TEXT NOT NULL DEFAULT 'balanced',
                cost_tier TEXT NOT NULL DEFAULT 'medium',
                is_active INTEGER NOT NULL DEFAULT 1,
                is_default INTEGER NOT NULL DEFAULT 0,
                priority INTEGER NOT NULL DEFAULT 50,
                health_status TEXT NOT NULL DEFAULT 'healthy',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_providers_active
            ON api_providers (is_active, priority DESC);
        """)
        conn.commit()

        # Check if table has rows, seed if empty
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM api_providers")
        count = cursor.fetchone()["cnt"]
        if count == 0:
            seed_default_providers(conn)


def seed_default_providers(conn: sqlite3.Connection) -> None:
    """Seed initial out-of-the-box provider models referencing environment variables."""
    seeds = [
        {
            "id": "groq/llama-3.1-8b-instant",
            "provider_name": "groq",
            "display_name": "Groq Llama 3.1 8B Instant (Lightweight)",
            "api_key_encrypted": "env:GROQ_API_KEY",
            "base_url": None,
            "model_name": "llama-3.1-8b-instant",
            "capability_tier": "LOW",
            "supported_tasks": ["text", "code", "classification", "summarization"],
            "context_window": 131072,
            "max_output_tokens": 8192,
            "latency_tier": "fast",
            "cost_tier": "low",
            "is_active": 1,
            "is_default": 0,
            "priority": 80,
            "health_status": "healthy",
        },
        {
            "id": "groq/llama-3.3-70b-versatile",
            "provider_name": "groq",
            "display_name": "Groq Llama 3.3 70B Versatile (Balanced)",
            "api_key_encrypted": "env:GROQ_API_KEY",
            "base_url": None,
            "model_name": "llama-3.3-70b-versatile",
            "capability_tier": "MEDIUM",
            "supported_tasks": ["text", "code", "tools", "reasoning", "extraction"],
            "context_window": 131072,
            "max_output_tokens": 8192,
            "latency_tier": "fast",
            "cost_tier": "low",
            "is_active": 1,
            "is_default": 1,
            "priority": 90,
            "health_status": "healthy",
        },
        {
            "id": "openai/gpt-4o-mini",
            "provider_name": "openai",
            "display_name": "OpenAI GPT-4o Mini (Balanced Fast)",
            "api_key_encrypted": "env:OPENAI_API_KEY",
            "base_url": None,
            "model_name": "gpt-4o-mini",
            "capability_tier": "MEDIUM",
            "supported_tasks": ["text", "code", "vision", "tools", "extraction"],
            "context_window": 128000,
            "max_output_tokens": 16384,
            "latency_tier": "fast",
            "cost_tier": "low",
            "is_active": 1,
            "is_default": 0,
            "priority": 75,
            "health_status": "healthy",
        },
        {
            "id": "openai/gpt-4o",
            "provider_name": "openai",
            "display_name": "OpenAI GPT-4o (High Performance)",
            "api_key_encrypted": "env:OPENAI_API_KEY",
            "base_url": None,
            "model_name": "gpt-4o",
            "capability_tier": "HIGH",
            "supported_tasks": ["text", "code", "vision", "tools", "complex_reasoning", "long_context"],
            "context_window": 128000,
            "max_output_tokens": 16384,
            "latency_tier": "balanced",
            "cost_tier": "high",
            "is_active": 1,
            "is_default": 0,
            "priority": 85,
            "health_status": "healthy",
        },
        {
            "id": "anthropic/claude-3-5-sonnet",
            "provider_name": "anthropic",
            "display_name": "Anthropic Claude 3.5 Sonnet (High Accuracy)",
            "api_key_encrypted": "env:ANTHROPIC_API_KEY",
            "base_url": None,
            "model_name": "claude-3-5-sonnet-20241022",
            "capability_tier": "HIGH",
            "supported_tasks": ["text", "code", "vision", "tools", "deep_research", "complex_planning", "long_context"],
            "context_window": 200000,
            "max_output_tokens": 8192,
            "latency_tier": "balanced",
            "cost_tier": "high",
            "is_active": 1,
            "is_default": 0,
            "priority": 95,
            "health_status": "healthy",
        },
        {
            "id": "deepseek/deepseek-chat",
            "provider_name": "deepseek",
            "display_name": "DeepSeek V3 (Reasoning & Coding)",
            "api_key_encrypted": "env:DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-chat",
            "capability_tier": "HIGH",
            "supported_tasks": ["text", "code", "tools", "reasoning", "long_context"],
            "context_window": 64000,
            "max_output_tokens": 8192,
            "latency_tier": "balanced",
            "cost_tier": "low",
            "is_active": 1,
            "is_default": 0,
            "priority": 80,
            "health_status": "healthy",
        },
        {
            "id": "local/llama3.2:3b",
            "provider_name": "local",
            "display_name": "Local Llama 3.2 3B (Offline Free)",
            "api_key_encrypted": "",
            "base_url": "http://localhost:11434/v1",
            "model_name": "llama3.2:3b",
            "capability_tier": "LOW",
            "supported_tasks": ["text"],
            "context_window": 8192,
            "max_output_tokens": 2048,
            "latency_tier": "fast",
            "cost_tier": "free",
            "is_active": 1,
            "is_default": 0,
            "priority": 40,
            "health_status": "healthy",
        },
    ]

    now = _now_iso()
    for s in seeds:
        conn.execute(
            """
            INSERT OR IGNORE INTO api_providers (
                id, provider_name, display_name, api_key_encrypted, base_url,
                model_name, capability_tier, supported_tasks, context_window,
                max_output_tokens, latency_tier, cost_tier, is_active, is_default,
                priority, health_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s["id"],
                s["provider_name"],
                s["display_name"],
                s["api_key_encrypted"],
                s["base_url"],
                s["model_name"],
                s["capability_tier"],
                json.dumps(s["supported_tasks"]),
                s["context_window"],
                s["max_output_tokens"],
                s["latency_tier"],
                s["cost_tier"],
                s["is_active"],
                s["is_default"],
                s["priority"],
                s["health_status"],
                now,
                now,
            ),
        )
    conn.commit()


def _row_to_record(row: sqlite3.Row) -> ApiProviderRecord:
    """Parse sqlite row into ApiProviderRecord."""
    supported_tasks = []
    if row["supported_tasks"]:
        try:
            supported_tasks = json.loads(row["supported_tasks"])
        except Exception:
            supported_tasks = [s.strip() for s in row["supported_tasks"].split(",") if s.strip()]

    tier_str = str(row["capability_tier"]).upper()
    try:
        tier = TaskTier(tier_str)
    except Exception:
        tier = TaskTier.MEDIUM

    return ApiProviderRecord(
        id=row["id"],
        provider_name=row["provider_name"],
        display_name=row["display_name"],
        api_key_encrypted=row["api_key_encrypted"] or "",
        base_url=row["base_url"],
        model_name=row["model_name"],
        capability_tier=tier,
        supported_tasks=supported_tasks,
        context_window=row["context_window"],
        max_output_tokens=row["max_output_tokens"],
        latency_tier=row["latency_tier"],
        cost_tier=row["cost_tier"],
        is_active=bool(row["is_active"]),
        is_default=bool(row["is_default"]),
        priority=row["priority"],
        health_status=row["health_status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProviderRepository:
    """Repository providing database operations for API provider models."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        init_db(self.db_path)

    def list_providers(self, active_only: bool = False) -> list[ApiProviderRecord]:
        """Fetch all providers from DB ordered by priority descending."""
        query = "SELECT * FROM api_providers"
        params: list[Any] = []
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY is_default DESC, priority DESC, created_at ASC"

        with get_connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [_row_to_record(r) for r in rows]

    def get_provider(self, provider_id: str) -> Optional[ApiProviderRecord]:
        """Fetch single provider by ID or model_name/id alias."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM api_providers WHERE id = ? OR model_name = ? LIMIT 1",
                (provider_id, provider_id)
            ).fetchone()
            if row:
                return _row_to_record(row)
        return None

    def get_default_provider(self) -> Optional[ApiProviderRecord]:
        """Fetch the default active provider, or highest priority active provider."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM api_providers WHERE is_active = 1 AND is_default = 1 ORDER BY priority DESC LIMIT 1"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM api_providers WHERE is_active = 1 ORDER BY priority DESC LIMIT 1"
                ).fetchone()
            if row:
                return _row_to_record(row)
        return None

    def create_provider(self, data: ApiProviderCreate) -> ApiProviderRecord:
        """Create and store a new provider record, encrypting any plaintext API key."""
        pid = data.id or re.sub(r"[^a-zA-Z0-9_-]", "-", f"{data.provider_name}-{data.model_name}").lower()
        if not data.id and self.get_provider(pid):
            pid = f"{pid}-{uuid.uuid4().hex[:6]}"

        encrypted_key = ""
        if data.api_key and data.api_key.strip():
            raw_key = data.api_key.strip()
            encrypted_key = encrypt_secret(raw_key)

        now = _now_iso()

        with get_connection(self.db_path) as conn:
            if data.is_default:
                conn.execute("UPDATE api_providers SET is_default = 0")

            conn.execute(
                """
                INSERT INTO api_providers (
                    id, provider_name, display_name, api_key_encrypted, base_url,
                    model_name, capability_tier, supported_tasks, context_window,
                    max_output_tokens, latency_tier, cost_tier, is_active, is_default,
                    priority, health_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    data.provider_name.strip(),
                    data.display_name.strip(),
                    encrypted_key,
                    data.base_url.strip() if data.base_url else None,
                    data.model_name.strip(),
                    data.capability_tier.value,
                    json.dumps(data.supported_tasks),
                    data.context_window,
                    data.max_output_tokens,
                    data.latency_tier,
                    data.cost_tier,
                    1 if data.is_active else 0,
                    1 if data.is_default else 0,
                    data.priority,
                    data.health_status,
                    now,
                    now,
                ),
            )
            conn.commit()

        created = self.get_provider(pid)
        if not created:
            raise RuntimeError(f"Failed to retrieve newly created provider {pid}")
        return created

    def update_provider(self, provider_id: str, data: ApiProviderUpdate) -> Optional[ApiProviderRecord]:
        """Update provider fields, re-encrypting key if supplied."""
        existing = self.get_provider(provider_id)
        if not existing:
            return None

        updates: list[str] = []
        values: list[Any] = []

        if data.provider_name is not None:
            updates.append("provider_name = ?")
            values.append(data.provider_name.strip())
        if data.display_name is not None:
            updates.append("display_name = ?")
            values.append(data.display_name.strip())
        if data.base_url is not None:
            updates.append("base_url = ?")
            values.append(data.base_url.strip() if data.base_url else None)
        if data.model_name is not None:
            updates.append("model_name = ?")
            values.append(data.model_name.strip())
        if data.capability_tier is not None:
            updates.append("capability_tier = ?")
            values.append(data.capability_tier.value)
        if data.supported_tasks is not None:
            updates.append("supported_tasks = ?")
            values.append(json.dumps(data.supported_tasks))
        if data.context_window is not None:
            updates.append("context_window = ?")
            values.append(data.context_window)
        if data.max_output_tokens is not None:
            updates.append("max_output_tokens = ?")
            values.append(data.max_output_tokens)
        if data.latency_tier is not None:
            updates.append("latency_tier = ?")
            values.append(data.latency_tier)
        if data.cost_tier is not None:
            updates.append("cost_tier = ?")
            values.append(data.cost_tier)
        if data.is_active is not None:
            updates.append("is_active = ?")
            values.append(1 if data.is_active else 0)
        if data.is_default is not None:
            updates.append("is_default = ?")
            values.append(1 if data.is_default else 0)
        if data.priority is not None:
            updates.append("priority = ?")
            values.append(data.priority)
        if data.health_status is not None:
            updates.append("health_status = ?")
            values.append(data.health_status)

        if data.api_key is not None:
            encrypted_key = encrypt_secret(data.api_key.strip()) if data.api_key.strip() else ""
            updates.append("api_key_encrypted = ?")
            values.append(encrypted_key)

        if not updates:
            return existing

        now = _now_iso()
        updates.append("updated_at = ?")
        values.append(now)

        values.append(existing.id)

        with get_connection(self.db_path) as conn:
            if data.is_default:
                conn.execute("UPDATE api_providers SET is_default = 0")

            set_clause = ", ".join(updates)
            conn.execute(f"UPDATE api_providers SET {set_clause} WHERE id = ?", values)
            conn.commit()

        return self.get_provider(existing.id)

    def delete_provider(self, provider_id: str, soft: bool = True) -> bool:
        """Delete or soft-deactivate provider."""
        existing = self.get_provider(provider_id)
        if not existing:
            return False

        with get_connection(self.db_path) as conn:
            if soft:
                conn.execute("UPDATE api_providers SET is_active = 0, updated_at = ? WHERE id = ?", (_now_iso(), existing.id))
            else:
                conn.execute("DELETE FROM api_providers WHERE id = ?", (existing.id,))
            conn.commit()
        return True

    def get_decrypted_key(self, provider_id: str) -> str:
        """Resolve decrypted key for provider, checking encrypted value then env reference."""
        provider = self.get_provider(provider_id)
        if not provider:
            return ""
        if not provider.api_key_encrypted:
            # Check default provider env var fallback
            default_env = f"{provider.provider_name.upper()}_API_KEY"
            return os.getenv(default_env, "")
        return decrypt_secret(provider.api_key_encrypted)


def provider_to_registry_entry(rec: ApiProviderRecord) -> ApiRegistryEntry:
    """Convert an ApiProviderRecord to an ApiRegistryEntry for scoring in the adaptive pipeline."""
    # Map supported tasks to Modality enum
    modalities = [Modality.TEXT]
    tasks_lower = [str(t).lower() for t in rec.supported_tasks]
    if any(t in tasks_lower for t in ["vision", "image", "multimodal"]):
        modalities.append(Modality.VISION)
    if any(t in tasks_lower for t in ["audio", "speech"]):
        modalities.append(Modality.AUDIO)
    if any(t in tasks_lower for t in ["code", "code_execution", "programming"]):
        modalities.append(Modality.CODE_EXECUTION)
    if any(t in tasks_lower for t in ["tools", "function_calling", "tool_use"]):
        modalities.append(Modality.TOOLS)
    if any(t in tasks_lower for t in ["web", "web_search", "search"]):
        modalities.append(Modality.WEB_SEARCH)

    # Cost tier mapping
    cost_str = str(rec.cost_tier).upper()
    try:
        cost_enum = CostTier(cost_str)
    except Exception:
        if "FREE" in cost_str:
            cost_enum = CostTier.FREE
        elif "LOW" in cost_str:
            cost_enum = CostTier.LOW
        elif "HIGH" in cost_str:
            cost_enum = CostTier.HIGH
        else:
            cost_enum = CostTier.MEDIUM

    # Latency tier mapping
    lat_str = str(rec.latency_tier).upper()
    try:
        lat_enum = LatencyTier(lat_str)
    except Exception:
        if "FAST" in lat_str:
            lat_enum = LatencyTier.FAST
        elif "SLOW" in lat_str:
            lat_enum = LatencyTier.SLOW
        else:
            lat_enum = LatencyTier.MODERATE

    # Check key availability
    key_avail = bool(rec.api_key_encrypted and rec.api_key_encrypted.strip())
    if not key_avail:
        env_fallback = f"{rec.provider_name.upper()}_API_KEY"
        key_avail = bool(os.getenv(env_fallback))

    # Derive required env vars if using env reference or standard provider
    required_env_vars: list[str] = []
    if rec.provider_name != "local":
        if rec.api_key_encrypted and rec.api_key_encrypted.startswith("env:"):
            required_env_vars.append(rec.api_key_encrypted[4:].strip())
        else:
            required_env_vars.append(f"{rec.provider_name.upper()}_API_KEY")

    return ApiRegistryEntry(
        id=rec.id,
        provider=rec.provider_name,
        model_name=rec.model_name,
        capability_tier=rec.capability_tier,
        context_window=rec.context_window,
        max_output_tokens=rec.max_output_tokens,
        supported_modalities=list(set(modalities)),
        cost_tier=cost_enum,
        latency_tier=lat_enum,
        rate_limit_rpm=60,
        required_env_vars=required_env_vars,
        base_url=rec.base_url,
        health_status=rec.health_status,
        enabled=rec.is_active and rec.health_status != "down",
        description=rec.display_name,
    )

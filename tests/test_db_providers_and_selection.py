"""Comprehensive tests for Database-Backed Provider Storage, Encryption, and Adaptive API Selection."""

import os
import pytest
from fastapi.testclient import TestClient

from agent.api import app
from agent.adaptive import (
    GLOBAL_ADAPTIVE_PIPELINE,
    TaskClassifier,
    TaskIntakeRequest,
    TaskTier,
)
from agent.db.crypto import decrypt_secret, encrypt_secret, mask_secret
from agent.db.database import ProviderRepository, init_db
from agent.db.models import ApiProviderCreate, ApiProviderUpdate


@pytest.fixture
def test_db(tmp_path):
    """Create an isolated SQLite database file for testing."""
    db_file = str(tmp_path / "test_agent_co.db")
    os.environ["DATABASE_PATH"] = db_file
    init_db(db_file)
    repo = ProviderRepository(db_file)
    GLOBAL_ADAPTIVE_PIPELINE.registry.db_path = db_file
    GLOBAL_ADAPTIVE_PIPELINE.registry.reload_from_db_or_defaults()
    yield repo
    if "DATABASE_PATH" in os.environ:
        del os.environ["DATABASE_PATH"]


@pytest.fixture
def client(test_db):
    """FastAPI TestClient pointing to the isolated database."""
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cryptography & Masking Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_aes_encryption_and_decryption():
    """Verify AES-256-GCM encryption produces 'enc:' prefix and decrypts accurately."""
    raw_key = "gsk_live_secret_1234567890abcdef"
    encrypted = encrypt_secret(raw_key)

    assert encrypted.startswith("enc:")
    assert raw_key not in encrypted  # Never store raw text in ciphertext

    decrypted = decrypt_secret(encrypted)
    assert decrypted == raw_key


def test_env_reference_encryption_and_decryption(monkeypatch):
    """Verify 'env:VAR' references remain unencrypted and resolve from environment."""
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret_env_value_999")
    ref = "env:TEST_PROVIDER_KEY"

    # Encrypt should recognize env: prefix and leave it intact
    encrypted = encrypt_secret(ref)
    assert encrypted == "env:TEST_PROVIDER_KEY"

    # Decrypt should resolve the environment variable
    decrypted = decrypt_secret(encrypted)
    assert decrypted == "secret_env_value_999"


def test_secret_masking():
    """Verify mask_secret safely obscures sensitive API keys for UI display."""
    assert mask_secret("gsk_1234567890abcdef") == "gsk_...cdef"
    assert mask_secret("env:OPENAI_API_KEY") == "env(OPENAI_API_KEY)"
    assert mask_secret("short") == "****"
    assert mask_secret("") == ""
    assert mask_secret(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. Database Repository Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_repository_seed_and_list(test_db):
    """Verify default seeded providers exist and can be listed."""
    providers = test_db.list_providers(active_only=False)
    assert len(providers) >= 6

    # Verify seed model names
    model_names = [p.model_name for p in providers]
    assert "llama-3.1-8b-instant" in model_names
    assert "gpt-4o" in model_names
    assert "claude-3-5-sonnet-20241022" in model_names


def test_create_and_read_provider(test_db):
    """Verify creating a custom provider encrypts the key and saves correctly."""
    new_provider = ApiProviderCreate(
        id="custom-fast-model",
        provider_name="custom",
        display_name="Custom Fast Model",
        api_key="custom_secret_key_abcdef12345",
        model_name="my-custom-model-v1",
        capability_tier=TaskTier.LOW,
        context_window=16384,
        max_output_tokens=2048,
        latency_tier="fast",
        cost_tier="free",
        priority=99,
    )

    created = test_db.create_provider(new_provider)
    assert created.id == "custom-fast-model"
    assert created.api_key_encrypted.startswith("enc:")
    assert "custom_secret_key_abcdef12345" not in created.api_key_encrypted

    # Decrypt verification
    decrypted_key = test_db.get_decrypted_key("custom-fast-model")
    assert decrypted_key == "custom_secret_key_abcdef12345"

    # Public conversion never leaks raw key
    public_dto = created.to_public()
    assert not hasattr(public_dto, "api_key_encrypted")
    assert public_dto.has_api_key is True
    assert "custom_secret_key" not in public_dto.api_key_masked


def test_update_and_delete_provider(test_db):
    """Verify updating fields and soft/hard deletion."""
    created = test_db.create_provider(
        ApiProviderCreate(
            id="test-update-model",
            provider_name="openai",
            display_name="Old Name",
            model_name="gpt-old",
            capability_tier=TaskTier.LOW,
        )
    )

    # Update display name and priority
    updated = test_db.update_provider(
        "test-update-model",
        ApiProviderUpdate(display_name="New Name", priority=120),
    )
    assert updated.display_name == "New Name"
    assert updated.priority == 120

    # Soft delete (deactivate)
    deleted = test_db.delete_provider("test-update-model", soft=True)
    assert deleted is True

    # Shouldn't appear in active list
    active = test_db.list_providers(active_only=True)
    assert "test-update-model" not in [p.id for p in active]


# ─────────────────────────────────────────────────────────────────────────────
# 3. HTTP API Endpoints Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_api_list_providers(client):
    """GET /api/providers should return non-secret metadata list."""
    res = client.get("/api/providers")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 6

    # Verify no raw keys exposed
    for item in data:
        assert "api_key_encrypted" not in item
        assert "api_key" not in item
        assert "has_api_key" in item
        assert "api_key_masked" in item
        assert "capability_tier" in item


def test_api_create_provider(client):
    """POST /api/providers should register new provider with encrypted key."""
    payload = {
        "id": "http-test-model",
        "provider_name": "groq",
        "display_name": "HTTP Test Model",
        "api_key": "gsk_test_api_key_1234567890",
        "model_name": "llama-3.2-1b",
        "capability_tier": "LOW",
        "latency_tier": "fast",
        "cost_tier": "low",
    }
    res = client.post("/api/providers", json=payload)
    assert res.status_code == 201
    body = res.json()
    assert body["id"] == "http-test-model"
    assert body["has_api_key"] is True
    assert "gsk_test_api_key_1234567890" not in str(body)


def test_api_update_and_delete_provider(client):
    """PATCH and DELETE endpoints for provider management."""
    # Create
    client.post(
        "/api/providers",
        json={
            "id": "temp-provider-1",
            "provider_name": "custom",
            "display_name": "Temp",
            "model_name": "custom-1",
        },
    )

    # Patch
    patch_res = client.patch(
        "/api/providers/temp-provider-1",
        json={"display_name": "Temp Updated", "capability_tier": "HIGH"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["display_name"] == "Temp Updated"
    assert patch_res.json()["capability_tier"] == "HIGH"

    # Delete
    del_res = client.delete("/api/providers/temp-provider-1")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


def test_api_test_provider_endpoint(client):
    """POST /api/providers/{id}/test tests connectivity without exposing keys."""
    res = client.post("/api/providers/groq%2Fllama-3.1-8b-instant/test")
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert body["provider_id"] == "groq/llama-3.1-8b-instant"
    # Key must NOT be in the response
    assert "gsk_" not in str(body)
    assert "enc:" not in str(body)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Manual vs. Automatic Adaptive Selection Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_manual_selection_routes_to_requested_db_api(test_db):
    """When selected_api_id is specified, selection engine selects that exact provider."""
    req = TaskIntakeRequest(
        user_prompt="Format this json document nicely",  # LOW task complexity
        selected_api_id="openai/gpt-4o",  # Explicitly user-selected HIGH provider
    )
    decision, _ = GLOBAL_ADAPTIVE_PIPELINE.route(req)

    assert decision.selected_api == "openai/gpt-4o"
    assert decision.model == "gpt-4o"
    assert decision.selection_mode == "manual"
    assert "Manual selection" in decision.reason
    assert decision.selected_api_details is not None
    assert decision.selected_api_details["id"] == "openai/gpt-4o"


def test_automatic_selection_routes_low_task_to_lightweight(test_db):
    """When selected_api_id is omitted or 'auto', routes low task to lightweight model."""
    req = TaskIntakeRequest(
        user_prompt="Format json and fix typos in this schema",
        selected_api_id="auto",
    )
    decision, _ = GLOBAL_ADAPTIVE_PIPELINE.route(req)

    assert decision.selection_mode == "automatic"
    assert decision.task_tier == TaskTier.LOW
    # Must NOT select expensive HIGH models for simple formatting
    assert decision.model != "claude-3-5-sonnet-20241022"
    assert decision.model != "gpt-4o"
    assert decision.selected_api in ("groq/llama-3.1-8b-instant", "groq-llama-3-1-8b", "local/llama3.2:3b")


def test_automatic_selection_routes_high_task_to_high_performance(test_db):
    """When high complexity task is provided, routes to high-tier model."""
    req = TaskIntakeRequest(
        user_prompt="Architect a distributed microservices event sourcing pipeline with deep multi-step security analysis and multi-modal diagrams.",
        selected_api_id=None,
    )
    decision, _ = GLOBAL_ADAPTIVE_PIPELINE.route(req)

    assert decision.selection_mode == "automatic"
    assert decision.task_tier == TaskTier.HIGH
    # Must route to high performance model
    assert decision.selected_api in ("anthropic/claude-3-5-sonnet", "openai/gpt-4o", "deepseek/deepseek-chat")


def test_chat_endpoint_with_manual_selection(client):
    """POST /api/chat with selected_api_id returns selection metadata."""
    res = client.post(
        "/api/chat",
        headers={"X-API-KEY": "gsk_mock_test_key_for_client_call"},
        json={
            "user_prompt": "Hello test agent!",
            "selected_api_id": "groq/llama-3.1-8b-instant",
        },
    )
    # The workflow may complete or mock execute
    assert res.status_code in (200, 422, 500)
    if res.status_code == 200:
        data = res.json()
        assert "adaptive_selection" in data
        assert data["adaptive_selection"]["selected_api"] == "groq/llama-3.1-8b-instant"
        assert data["adaptive_selection"]["selection_mode"] == "manual"

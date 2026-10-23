"""Tests for user authentication and session management in Rorak AI."""

import pytest
from fastapi.testclient import TestClient
from agent.api import app
from agent.core.security import decode_access_token


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_register_and_login_flow(client):
    email = "new_user_flow@test.com"
    password = "secure_password_123"
    name = "New User"

    # Register
    reg_res = client.post("/auth/register", json={"email": email, "password": password, "name": name})
    assert reg_res.status_code == 200
    data = reg_res.json()
    assert data["email"] == email
    assert data["name"] == name
    assert "id" in data

    # Login
    login_res = client.post("/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    login_data = login_res.json()
    token = login_data["access_token"]
    assert token is not None

    # Check JWT format & claims
    parts = token.split(".")
    assert len(parts) == 3
    payload = decode_access_token(token)
    assert payload["sub"] == data["id"]
    assert payload["email"] == email
    assert "exp" in payload

    # Authenticated /auth/me
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email


def test_auth_login_auto_provisions_new_user(client):
    email = "auto_provision_user@test.com"
    password = "any_password_123"

    login_res = client.post("/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["user"]["email"] == email
    assert "access_token" in data
    assert len(data["access_token"].split(".")) == 3


def test_auth_me_unauthenticated_fallback(client):
    # Unauthenticated /auth/me should gracefully return a fallback guest user, not 401 or 500
    res = client.get("/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert "email" in data
    assert "id" in data


def test_authenticated_conversations_and_chat(client):
    email = "chat_tester@test.com"
    password = "password123"
    login_res = client.post("/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # List conversations
    conv_list = client.get("/conversations/?page=1&page_size=50", headers=headers)
    assert conv_list.status_code == 200
    assert "conversations" in conv_list.json()
    assert "pagination" in conv_list.json()

    # Create conversation
    create_res = client.post("/conversations/", json={"title": "Session Chat"}, headers=headers)
    assert create_res.status_code == 200
    conv_id = create_res.json()["id"]

    # Post message in chat
    chat_res = client.post("/chat/", json={"question": "What is 2+2?", "conversation_id": conv_id}, headers=headers)
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "answer" in chat_data
    assert "message" in chat_data
    assert chat_data["conversation_id"] == conv_id

    # Get messages
    msgs_res = client.get(f"/conversations/{conv_id}/messages", headers=headers)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"

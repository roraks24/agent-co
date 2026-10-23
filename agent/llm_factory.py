"""Factory for creating chat models used by the API workflow endpoints."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq

PROVIDER_NAME = "groq"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def build_chat_model(api_key: str, model: str | None = None) -> BaseChatModel:
    token = (api_key or "").strip()
    if not token:
        raise ValueError("api_key is required.")

    selected_model = (model or DEFAULT_GROQ_MODEL).strip()
    return ChatGroq(api_key=token, model=selected_model)

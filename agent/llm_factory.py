"""Factory for creating chat models supporting multiple providers and custom keys."""

from __future__ import annotations

import os
from typing import Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel

PROVIDER_NAME = "groq"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def build_chat_model(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    custom_keys: Optional[dict[str, Any]] = None,
) -> BaseChatModel:
    """Build LangChain chat model with multi-provider and custom key support."""
    if isinstance(custom_keys, dict):
        provider = custom_keys.get("provider") or provider
        prov_key = f"{provider}_api_key" if provider else None
        api_key = (
            (custom_keys.get(prov_key) if prov_key else None)
            or custom_keys.get("api_key")
            or custom_keys.get("groq_api_key")
            or custom_keys.get("openai_api_key")
            or custom_keys.get("custom_api_key")
            or api_key
        )
        model = custom_keys.get("model") or custom_keys.get("custom_model") or model
        base_url = custom_keys.get("base_url") or custom_keys.get("custom_base_url") or base_url

    norm_provider = (provider or "").lower().strip()
    if not norm_provider:
        if base_url:
            norm_provider = "custom"
        elif api_key and api_key.startswith("gsk_"):
            norm_provider = "groq"
        elif api_key and (api_key.startswith("sk-") or api_key.startswith("sess-")):
            norm_provider = "openai"
        else:
            norm_provider = "groq"

    if norm_provider == "groq":
        from langchain_groq import ChatGroq

        key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
        if not key:
            raise ValueError("api_key is required for Groq.")
        selected_model = (model or DEFAULT_GROQ_MODEL).strip()
        return ChatGroq(api_key=key, model=selected_model, temperature=temperature)

    elif norm_provider == "openai":
        from langchain_openai import ChatOpenAI

        key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not key:
            raise ValueError("api_key is required for OpenAI.")
        selected_model = (model or "gpt-4o").strip()
        return ChatOpenAI(api_key=key, model=selected_model, temperature=temperature)

    elif norm_provider in ("custom", "openai_compatible", "ollama", "openrouter", "deepseek", "local"):
        from langchain_openai import ChatOpenAI

        url = (base_url or "http://localhost:11434/v1").strip()
        key = (api_key or os.getenv("OPENAI_API_KEY", "custom-key")).strip()
        selected_model = (model or "default").strip()
        return ChatOpenAI(base_url=url, api_key=key, model=selected_model, temperature=temperature)

    else:
        from langchain_groq import ChatGroq

        key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
        if not key:
            raise ValueError(f"api_key is required for provider '{norm_provider}'.")
        selected_model = (model or DEFAULT_GROQ_MODEL).strip()
        return ChatGroq(api_key=key, model=selected_model, temperature=temperature)

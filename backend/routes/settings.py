"""Settings and external API key validation routes."""

import logging
import os
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.config import GROQ_API_KEY, GROQ_MODEL, TAVILY_API_KEY

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/settings",
    tags=["Settings & Custom Keys"],
)


class ValidateKeyRequest(BaseModel):
    provider: str = Field(..., description="Provider name: groq, openai, custom, tavily")
    api_key: Optional[str] = Field(default=None, description="The custom API key to test")
    base_url: Optional[str] = Field(default=None, description="Custom OpenAI-compatible base URL")
    model: Optional[str] = Field(default=None, description="Model identifier to test")


class ValidateKeyResponse(BaseModel):
    valid: bool
    provider: str
    message: str
    error: Optional[str] = None
    tested_model: Optional[str] = None


@router.get("/keys-status")
def get_keys_status() -> dict[str, Any]:
    """Return backend status indicating which external providers have server-level keys configured."""
    return {
        "server_groq_configured": bool(GROQ_API_KEY),
        "server_tavily_configured": bool(TAVILY_API_KEY),
        "server_openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "default_model": GROQ_MODEL,
    }


@router.post("/validate-key", response_model=ValidateKeyResponse)
def validate_custom_key(req: ValidateKeyRequest) -> ValidateKeyResponse:
    """
    Test and validate an external API key or custom endpoint.
    Performs a minimal live completion or check against the provider to confirm credentials.
    """
    provider = req.provider.lower().strip()
    key = (req.api_key or "").strip()

    # 1. Groq Validation
    if provider == "groq":
        if not key:
            return ValidateKeyResponse(
                valid=False,
                provider="groq",
                message="Validation failed: API key is empty.",
                error="Please enter a valid Groq API key starting with 'gsk_'.",
            )
        try:
            from groq import Groq
            test_client = Groq(api_key=key, timeout=10.0)
            target_model = req.model or GROQ_MODEL or "openai/gpt-oss-120b"
            resp = test_client.chat.completions.create(
                model=target_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=2,
            )
            return ValidateKeyResponse(
                valid=True,
                provider="groq",
                message=f"Groq API key is valid! Connected to model '{target_model}'.",
                tested_model=target_model,
            )
        except Exception as exc:
            err_msg = str(exc)
            logger.warning("Groq custom key validation failed: %s", err_msg)
            return ValidateKeyResponse(
                valid=False,
                provider="groq",
                message="Failed to validate Groq API key.",
                error=err_msg,
            )

    # 2. OpenAI Validation
    elif provider == "openai":
        if not key:
            return ValidateKeyResponse(
                valid=False,
                provider="openai",
                message="Validation failed: API key is empty.",
                error="Please enter a valid OpenAI API key starting with 'sk-'.",
            )
        try:
            import openai
            test_client = openai.OpenAI(api_key=key, timeout=10.0)
            target_model = req.model or "gpt-4o-mini"
            resp = test_client.chat.completions.create(
                model=target_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=2,
            )
            return ValidateKeyResponse(
                valid=True,
                provider="openai",
                message=f"OpenAI API key is valid! Connected to model '{target_model}'.",
                tested_model=target_model,
            )
        except Exception as exc:
            err_msg = str(exc)
            logger.warning("OpenAI custom key validation failed: %s", err_msg)
            return ValidateKeyResponse(
                valid=False,
                provider="openai",
                message="Failed to validate OpenAI API key.",
                error=err_msg,
            )

    # 3. Custom OpenAI-Compatible (Ollama, OpenRouter, DeepSeek, LocalAI)
    elif provider in ("custom", "openai_compatible", "ollama", "openrouter", "deepseek", "local"):
        base_url = (req.base_url or "http://localhost:11434/v1").strip()
        try:
            import openai
            test_client = openai.OpenAI(
                base_url=base_url,
                api_key=key or "custom-key",
                timeout=10.0,
            )
            target_model = req.model or "default"
            resp = test_client.chat.completions.create(
                model=target_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=2,
            )
            return ValidateKeyResponse(
                valid=True,
                provider="custom",
                message=f"Connected successfully to endpoint '{base_url}' (model: {target_model})!",
                tested_model=target_model,
            )
        except Exception as exc:
            err_msg = str(exc)
            logger.warning("Custom endpoint validation failed: %s", err_msg)
            return ValidateKeyResponse(
                valid=False,
                provider="custom",
                message=f"Failed to connect to endpoint '{base_url}'.",
                error=err_msg,
            )

    # 4. Tavily Search Validation
    elif provider == "tavily":
        if not key:
            return ValidateKeyResponse(
                valid=False,
                provider="tavily",
                message="Validation failed: Tavily API key is empty.",
                error="Please enter a valid Tavily API key starting with 'tvly-'.",
            )
        try:
            import json
            import urllib.request
            req_data = json.dumps({
                "api_key": key,
                "query": "test",
                "max_results": 1,
            }).encode("utf-8")
            h_req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(h_req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                if "results" in data:
                    return ValidateKeyResponse(
                        valid=True,
                        provider="tavily",
                        message="Tavily Search API key verified successfully!",
                    )
                else:
                    return ValidateKeyResponse(
                        valid=False,
                        provider="tavily",
                        message="Unexpected response from Tavily API.",
                        error=str(data),
                    )
        except Exception as exc:
            return ValidateKeyResponse(
                valid=False,
                provider="tavily",
                message="Failed to validate Tavily API key.",
                error=str(exc),
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Supported: groq, openai, custom, tavily.",
        )

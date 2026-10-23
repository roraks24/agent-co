"""Prompt composition utilities for guarded node-specific prompts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.prompts import IMMUTABLE_PROMPT_RULES, MAX_MUTABLE_PROMPT_CHARS, NODE_CONFIG


@dataclass(frozen=True)
class NodePromptConfig:
    immutable_prefix: str
    default_mutable: str


NODE_PROMPT_CONFIGS: dict[str, NodePromptConfig] = {
    node_id: NodePromptConfig(**payload) for node_id, payload in NODE_CONFIG.items()
}


def _plan_to_text(plan: Any) -> str:
    if hasattr(plan, "model_dump_json"):
        return plan.model_dump_json(indent=2)
    return str(plan)


def _get_node_prompt(node_id: str) -> NodePromptConfig:
    node_prompt = NODE_PROMPT_CONFIGS.get(node_id)
    if node_prompt is None:
        raise ValueError(f"Unsupported prompt node_id: {node_id}")
    return node_prompt


def _validate_length(text: str, source: str) -> str:
    if len(text) > MAX_MUTABLE_PROMPT_CHARS:
        raise ValueError(
            f"{source} exceeds {MAX_MUTABLE_PROMPT_CHARS} characters. "
            f"Current length: {len(text)}"
        )
    return text


def _normalize_mutable_layer(mutable_layer: str | None, default_mutable: str) -> str:
    candidate = mutable_layer if mutable_layer is not None else default_mutable
    candidate = candidate or ""

    if not candidate.strip():
        fallback = default_mutable or ""
        candidate = fallback if fallback.strip() else "No mutable prompt provided."

    return _validate_length(candidate, "Mutable prompt")


def resolve_mutable_for_node(
    node_id: str,
    prompt_overrides: dict[str, str] | None,
    legacy_mutable_prompt: str | None,
) -> str:
    node_prompt = _get_node_prompt(node_id)

    if isinstance(prompt_overrides, dict):
        override_value = prompt_overrides.get(node_id)
        if isinstance(override_value, str) and override_value.strip():
            return _validate_length(override_value, f"prompt_overrides.{node_id}")

    if isinstance(legacy_mutable_prompt, str) and legacy_mutable_prompt.strip():
        return _validate_length(legacy_mutable_prompt, "mutable_prompt")

    return _normalize_mutable_layer(None, node_prompt.default_mutable)


def default_mutable_for_node(node_id: str) -> str:
    return _get_node_prompt(node_id).default_mutable


def get_composed_prompt(node_id: str, user_content: str | None, context_block: str) -> str:
    node_prompt = _get_node_prompt(node_id)
    mutable_text = _normalize_mutable_layer(user_content, node_prompt.default_mutable)
    immutable_rules = "\n".join(f"- {rule}" for rule in IMMUTABLE_PROMPT_RULES)

    sections = [
        "GLOBAL IMMUTABLE RULES (HIGHEST PRIORITY):\n" + immutable_rules,
        node_prompt.immutable_prefix.strip(),
        "MUTABLE LAYER (USER EDITABLE):\n" + mutable_text.strip(),
        context_block.strip(),
    ]
    return "\n\n".join(section for section in sections if section)


def guarded_prompt_policy() -> dict[str, Any]:
    return {
        "max_mutable_prompt_chars": MAX_MUTABLE_PROMPT_CHARS,
        "immutable_rules": IMMUTABLE_PROMPT_RULES,
    }


def prompt_schema() -> dict[str, Any]:
    return {
        "nodes": NODE_CONFIG,
        "policy": guarded_prompt_policy(),
    }


def planner_prompt(user_prompt: str, mutable_layer: str | None = None) -> str:
    instructions = (
        "Objective Planning Instructions:\n"
        "Analyze the user's objective and formulate an ordered GoalPlan with executable ActionSteps.\n"
        "Supported task types: 'research', 'coding', 'analysis', 'general'.\n"
        "Available registered tools: 'get_github_repo_metadata', 'web_search', 'fetch_url_content', 'write_file', 'read_file', 'list_files'.\n"
        "Rules:\n"
        "1. For open-source framework research / comparison tasks: Start with 'get_github_repo_metadata' for each target project (e.g. repo: 'langchain-ai/langgraph', 'crewAIInc/crewAI', 'microsoft/autogen') to retrieve official star counts, licenses, and releases. Follow with 'web_search' for architectural trade-offs, and conclude with 'write_file' for the grounded Markdown report.\n"
        "2. For coding tasks: Include write_file steps for source code, requirements.txt, and README.md.\n"
        "3. Provide clear expected outcomes and success criteria for each step.\n"
        "4. Tool arguments must be valid (e.g. get_github_repo_metadata needs 'repo'; web_search needs 'query'; write_file needs 'path')."
    )
    return get_composed_prompt(
        "planner",
        mutable_layer,
        f"{instructions}\n\nUser Request:\n{user_prompt}",
    )


def architecture_prompt(plan: Any, mutable_layer: str | None = None) -> str:
    return get_composed_prompt(
        "architect",
        mutable_layer,
        f"Plan:\n{_plan_to_text(plan)}",
    )


def coder_system_prompt(mutable_layer: str | None = None) -> str:
    return get_composed_prompt(
        "coder",
        mutable_layer,
        "Execution Mode: Execute action step with registered tools and record verified evidence.",
    )

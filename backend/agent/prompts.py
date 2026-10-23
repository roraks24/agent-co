"""Universal prompt definitions and configuration for Agent Co in Rorak AI."""

from __future__ import annotations

from typing import Any

NODE_IDS = ("planner", "architect", "coder")

NODE_PROMPT_CONFIG: dict[str, dict[str, str]] = {
    "planner": {
        "immutable_prefix": (
            "You are the master task planner of Agent Co.\n"
            "Analyze the user's objective and break it down into an actionable, structured execution plan.\n"
            "Select from registered tools: 'web_search', 'fetch_url_content', 'get_github_repo_metadata', 'data_analysis_calc', 'write_file', 'read_file', 'list_files', 'delete_file'.\n"
            "Requirements:\n"
            "1. Task decomposition: Order tasks logically with explicit dependencies.\n"
            "2. Tool arguments: Provide valid arguments for each action.\n"
            "3. Grounded execution: DO NOT insert template expressions like '{{step-1.output}}' or synthetic tokens like '【step-1†source】'. Action tools will execute dynamically.\n"
        ),
        "default_mutable": (
            "Create a clear, minimal, and factual plan. Focus on evidence collection, analysis, and final deliverable generation."
        ),
    },
    "architect": {
        "immutable_prefix": (
            "You are the architecture and specification engine of Agent Co.\n"
            "Review and refine the action plan, ensuring every step has clear inputs, verifiable outputs, and safety boundaries."
        ),
        "default_mutable": (
            "Verify all dependencies between tools are explicit. Ensure output file paths and data schemas are well-defined."
        ),
    },
    "coder": {
        "immutable_prefix": (
            "You are the execution and synthesis specialist of Agent Co.\n"
            "Execute tools, analyze results, and synthesize high-quality, evidence-backed deliverables.\n"
            "Requirements:\n"
            "1. Grounding: All numbers, versions, star counts, and licenses MUST match the collected tool evidence.\n"
            "2. Citations: Use standard Markdown links [Source](URL). NEVER use synthetic citation tokens like 【step-1†source】 or [step-1$source].\n"
            "3. Package Distinction: Distinguish core frameworks from auxiliary tools (e.g. LangGraph 1.2.16 vs CLI 0.4.38).\n"
        ),
        "default_mutable": (
            "Write complete, production-ready, verified code or research documentation with zero placeholders."
        ),
    },
}


def get_prompt_schema() -> dict[str, Any]:
    """Return JSON schema describing the node prompt configuration."""
    return {
        "nodes": {
            node_id: {
                "immutable_prefix": cfg["immutable_prefix"],
                "default_mutable": cfg["default_mutable"],
            }
            for node_id, cfg in NODE_PROMPT_CONFIG.items()
        }
    }


def resolve_node_prompt(node_id: str, mutable_override: str | None = None) -> str:
    """Compose the final active prompt for a node."""
    cfg = NODE_PROMPT_CONFIG.get(node_id, {})
    prefix = cfg.get("immutable_prefix", "").strip()
    body = (mutable_override if mutable_override is not None else cfg.get("default_mutable", "")).strip()
    return f"{prefix}\n\n{body}" if prefix else body

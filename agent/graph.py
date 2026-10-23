"""LangGraph workflow for objective planning -> task architecture -> tool execution -> verification."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from time import perf_counter
from typing import Any, AsyncIterator, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import tool
from langgraph.constants import END
from langgraph.graph import StateGraph

try:
    from .verification_engine import FactualVerifier
    from .prompts import (
        architecture_prompt,
        coder_system_prompt,
        resolve_mutable_for_node,
        planner_prompt,
    )
    from .state import (
        ActionExecutionRecord,
        ActionStep,
        AgentState,
        CoderState,
        FileSpec,
        GoalPlan,
        ImplementationStep,
        Plan,
        TaskPlan,
        VerificationResult,
    )
    from .tools import list_files, read_file, write_file
    from .tools_registry import GLOBAL_TOOL_REGISTRY, redact_sensitive_data
    from .workspace import read_text_file
except ImportError:  # pragma: no cover
    from verification_engine import FactualVerifier
    from prompts import (
        architecture_prompt,
        coder_system_prompt,
        resolve_mutable_for_node,
        planner_prompt,
    )
    from state import (
        ActionExecutionRecord,
        ActionStep,
        AgentState,
        CoderState,
        FileSpec,
        GoalPlan,
        ImplementationStep,
        Plan,
        TaskPlan,
        VerificationResult,
    )
    from tools import list_files, read_file, write_file
    from tools_registry import GLOBAL_TOOL_REGISTRY, redact_sensitive_data
    from workspace import read_text_file

logger = logging.getLogger(__name__)

GraphEvent = dict[str, Any]
EventCallback = Callable[[GraphEvent], None]


def _emit(event_callback: EventCallback | None, event_type: str, **payload: Any) -> None:
    if event_callback is None:
        return
    event_callback({"event": event_type, **payload})


def _resolve_node_mutable_prompt(state: AgentState, node_id: str) -> str:
    prompt_overrides = state.get("prompt_overrides") or {}
    legacy_mutable = state.get("mutable_prompt")
    return resolve_mutable_for_node(node_id, prompt_overrides, legacy_mutable)


@tool
def _list_workspace_files(_: str = ".") -> str:
    """Lists files in the active generated project workspace."""
    return list_files.run(".")


def _build_coder_tools() -> list[Any]:
    return [read_file, write_file, _list_workspace_files]


def _goal_plan_from_legacy_plan(plan: Plan) -> GoalPlan:
    steps: list[ActionStep] = []
    for i, file_spec in enumerate(plan.files):
        steps.append(
            ActionStep(
                id=f"step-{i+1}",
                title=f"Write {file_spec.path}",
                tool_name="write_file",
                tool_args={"path": file_spec.path, "content": ""},
                expected_outcome=file_spec.purpose,
                success_criteria=f"File '{file_spec.path}' exists and is non-empty.",
            )
        )
    return GoalPlan(
        objective=plan.name,
        task_type="coding",
        expected_outcome=plan.description,
        steps=steps,
    )


def _legacy_plan_from_goal_plan(goal_plan: GoalPlan) -> Plan:
    files: list[FileSpec] = [
        FileSpec(
            path=s.tool_args.get("path", f"{s.id}.md"),
            purpose=s.expected_outcome or s.title,
        )
        for s in goal_plan.steps
        if s.tool_name == "write_file"
    ]
    if not files:
        files = [FileSpec(path="output.md", purpose=goal_plan.expected_outcome or "Deliverable")]

    return Plan(
        name=goal_plan.objective[:50],
        description=goal_plan.expected_outcome[:160] or goal_plan.objective,
        techstack=goal_plan.task_type,
        features=[s.title for s in goal_plan.steps],
        files=files,
    )


def _evaluate_goal_completion(
    goal_plan: GoalPlan,
    execution_records: list[ActionExecutionRecord],
) -> VerificationResult:
    """Evaluate objective fulfillment against actual tool execution evidence."""
    verifier = FactualVerifier(goal_plan, execution_records)
    return verifier.evaluate()


def _generate_deliverable_summary(
    goal_plan: GoalPlan,
    execution_records: list[ActionExecutionRecord],
    verification: VerificationResult,
) -> str:
    """Format an executive markdown report summarizing the execution."""
    successful_tools = [r.tool_name for r in execution_records if r.status == "success"]
    tools_str = ", ".join(sorted(set(successful_tools))) if successful_tools else "None"

    lines = [
        f"## Execution Report: {goal_plan.objective}",
        f"**Status:** {verification.objective_status}  ",
        f"**Task Category:** {goal_plan.task_type}  ",
        f"**Tools Utilized:** {tools_str}  ",
        "",
        "### Verification & Assessment",
        verification.evidence_summary,
        "",
        "### Criteria Evaluated",
    ]
    for c in verification.criteria_evaluated:
        lines.append(f"- {c}")

    lines.append("")
    lines.append("### Deliverables")
    write_records = [r for r in execution_records if r.tool_name == "write_file" and r.status == "success"]
    if write_records:
        for wr in write_records:
            path = wr.tool_args.get("path", "file")
            lines.append(f"- `{path}` (generated and verified in workspace)")
    else:
        lines.append("- Output presented in execution record.")

    return "\n".join(lines)


def _parse_llm_json_goal_plan(text: str, user_prompt: str) -> GoalPlan | None:
    """Parse JSON or markdown-fenced JSON into a structured GoalPlan."""
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", clean)
    if match:
        clean = match.group(1)
    else:
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start : end + 1]

    import json

    try:
        data = json.loads(clean)
    except Exception:
        return None

    if "GoalPlan" in data and isinstance(data["GoalPlan"], dict):
        data = data["GoalPlan"]

    obj = data.get("objective") or data.get("goal") or user_prompt
    task_type = data.get("task_type") or ("research" if "research" in user_prompt.lower() else "general")
    expected_outcome = data.get("expected_outcome") or str(
        data.get("success_criteria") or "Completed workflow execution"
    )

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) == 0:
        return None

    normalized_steps: list[ActionStep] = []
    for i, s in enumerate(raw_steps):
        if isinstance(s, dict):
            s_id = s.get("id") or f"step-{i+1}"
            s_title = s.get("title") or s.get("description") or f"Step {i+1}"
            s_tool = s.get("tool_name") or s.get("tool") or "write_file"
            s_args = s.get("tool_args") or s.get("args") or {}
            s_outcome = s.get("expected_outcome") or s.get("description") or ""
            s_crit = s.get("success_criteria") or ""
            normalized_steps.append(
                ActionStep(
                    id=s_id,
                    title=s_title,
                    tool_name=s_tool,
                    tool_args=s_args,
                    expected_outcome=s_outcome,
                    success_criteria=s_crit,
                )
            )

    if not normalized_steps:
        return None

    return GoalPlan(
        objective=obj,
        task_type=task_type,
        expected_outcome=expected_outcome,
        steps=normalized_steps,
    )


def _planner_agent(
    llm: BaseChatModel,
    event_callback: EventCallback | None,
) -> Callable[[AgentState], dict[str, Any]]:
    def planner(state: AgentState) -> dict[str, Any]:
        user_prompt = str(state.get("user_prompt", "")).strip()
        mutable_prompt = _resolve_node_mutable_prompt(state, "planner")

        if not user_prompt:
            raise ValueError("user_prompt must not be empty.")

        _emit(event_callback, "node_start", node="planner")

        goal_plan: GoalPlan | None = None
        plan: Plan | None = None

        # Attempt general-purpose GoalPlan extraction
        try:
            composed_prompt = planner_prompt(user_prompt, mutable_layer=mutable_prompt)
            llm_result = llm.invoke(composed_prompt)
            text_candidate = getattr(llm_result, "content", str(llm_result))
            parsed_gp = _parse_llm_json_goal_plan(text_candidate, user_prompt)
            if parsed_gp:
                goal_plan = parsed_gp
                plan = _legacy_plan_from_goal_plan(goal_plan)
            else:
                response = llm.with_structured_output(GoalPlan).invoke(composed_prompt)
                if isinstance(response, GoalPlan):
                    goal_plan = response
                    plan = _legacy_plan_from_goal_plan(goal_plan)
                elif isinstance(response, Plan):
                    plan = response
                    goal_plan = _goal_plan_from_legacy_plan(plan)
                elif isinstance(response, dict):
                    if "steps" in response:
                        goal_plan = GoalPlan(**response)
                        plan = _legacy_plan_from_goal_plan(goal_plan)
                    elif "files" in response:
                        plan = Plan(**response)
                        goal_plan = _goal_plan_from_legacy_plan(plan)
        except Exception as exc:
            logger.warning("GoalPlan extraction fell back to legacy Plan: %s", exc)
            response = llm.with_structured_output(Plan).invoke(
                planner_prompt(user_prompt, mutable_layer=mutable_prompt)
            )
            if response is None:
                raise ValueError("Planner returned no response.")
            if isinstance(response, Plan):
                plan = response
                goal_plan = _goal_plan_from_legacy_plan(plan)
            elif isinstance(response, GoalPlan):
                goal_plan = response
                plan = _legacy_plan_from_goal_plan(goal_plan)

        if goal_plan is None or plan is None:
            raise ValueError("Planner failed to build an executable plan.")

        _emit(
            event_callback,
            "action_plan",
            objective=goal_plan.objective,
            task_type=goal_plan.task_type,
            step_count=len(goal_plan.steps),
            steps=[s.model_dump() for s in goal_plan.steps],
        )

        _emit(
            event_callback,
            "node_complete",
            node="planner",
            file_count=len(plan.files),
            feature_count=len(plan.features),
            task_type=goal_plan.task_type,
        )
        return {
            "plan": plan,
            "goal_plan": goal_plan,
            "task_type": goal_plan.task_type,
        }

    return planner


def _architect_agent(
    llm: BaseChatModel,
    event_callback: EventCallback | None,
) -> Callable[[AgentState], dict[str, Any]]:
    def architect(state: AgentState) -> dict[str, Any]:
        plan = state.get("plan")
        goal_plan = state.get("goal_plan")

        _emit(event_callback, "node_start", node="architect")

        if goal_plan is not None and goal_plan.steps:
            # Normalize and validate step tool assignments
            registered_tool_names = set(t["name"] for t in GLOBAL_TOOL_REGISTRY.list_tools())
            for step in goal_plan.steps:
                if step.tool_name not in registered_tool_names:
                    name_lower = step.tool_name.lower()
                    if "search" in name_lower:
                        step.tool_name = "web_search"
                    elif "fetch" in name_lower or "url" in name_lower:
                        step.tool_name = "fetch_url_content"
                    elif "read" in name_lower:
                        step.tool_name = "read_file"
                    elif "list" in name_lower:
                        step.tool_name = "list_files"
                    else:
                        step.tool_name = "write_file"

            task_steps = [
                ImplementationStep(
                    file_path=step.tool_args.get("path", f"{step.id}.md"),
                    task_description=f"Tool: {step.tool_name}. Goal: {step.title}. Expected: {step.expected_outcome}",
                )
                for step in goal_plan.steps
            ]
            response = TaskPlan(implementation_steps=task_steps)
            response.plan = plan
        else:
            mutable_prompt = _resolve_node_mutable_prompt(state, "architect")
            response = llm.with_structured_output(TaskPlan).invoke(
                architecture_prompt(plan, mutable_layer=mutable_prompt)
            )
            if response is None:
                raise ValueError("Architect returned no response.")
            response.plan = plan
            goal_plan = GoalPlan(
                objective=plan.name if plan else "Execute task",
                task_type="coding",
                expected_outcome=plan.description if plan else "",
                steps=[
                    ActionStep(
                        id=f"step-{i+1}",
                        title=f"Implement {s.file_path}",
                        tool_name="write_file",
                        tool_args={"path": s.file_path, "content": ""},
                        expected_outcome=s.task_description,
                    )
                    for i, s in enumerate(response.implementation_steps)
                ],
            )

        _emit(
            event_callback,
            "node_complete",
            node="architect",
            step_count=len(response.implementation_steps),
        )
        return {"detailed_ins": response, "goal_plan": goal_plan}

    return architect


def _coder_agent(
    llm: BaseChatModel,
    event_callback: EventCallback | None,
) -> Callable[[AgentState], dict[str, Any]]:
    def coder(state: AgentState) -> dict[str, Any]:
        goal_plan = state.get("goal_plan")
        if goal_plan is None:
            # Fallback from detailed_ins
            detailed_ins = state.get("detailed_ins")
            if detailed_ins:
                goal_plan = GoalPlan(
                    objective=state.get("user_prompt", "Coding Task"),
                    task_type="coding",
                    expected_outcome="Implemented application files",
                    steps=[
                        ActionStep(
                            id=f"step-{i+1}",
                            title=f"Write {s.file_path}",
                            tool_name="write_file",
                            tool_args={"path": s.file_path, "content": ""},
                            expected_outcome=s.task_description,
                        )
                        for i, s in enumerate(detailed_ins.implementation_steps)
                    ],
                )
            else:
                raise ValueError("No goal plan or detailed instructions available for execution.")

        execution_records = list(state.get("execution_records") or [])
        current_step_idx = state.get("current_step_idx", 0)
        steps = goal_plan.steps

        # Check if all steps have been executed
        if current_step_idx >= len(steps):
            verification = _evaluate_goal_completion(goal_plan, execution_records)
            final_summary = _generate_deliverable_summary(goal_plan, execution_records, verification)

            _emit(
                event_callback,
                "verification_complete",
                objective_status=verification.objective_status,
                evidence_summary=verification.evidence_summary,
                criteria_evaluated=verification.criteria_evaluated,
                final_summary=final_summary,
            )
            _emit(
                event_callback,
                "node_complete",
                node="coder",
                status="DONE",
                objective_status=verification.objective_status,
            )

            coder_state = state.get("coder_state") or CoderState(
                task_plan=state.get("detailed_ins") or TaskPlan(implementation_steps=[]),
                current_step_idx=current_step_idx,
            )

            return {
                "status": "DONE",
                "objective_status": verification.objective_status,
                "verification": verification,
                "final_summary": final_summary,
                "execution_records": execution_records,
                "coder_state": coder_state,
            }

        # Execute the current step
        step = steps[current_step_idx]
        step.status = "running"
        tool_name = step.tool_name
        tool_args = dict(step.tool_args)

        _emit(
            event_callback,
            "tool_start",
            step_id=step.id,
            tool_name=tool_name,
            tool_args=redact_sensitive_data(tool_args),
            title=step.title,
            step_index=current_step_idx,
            total_steps=len(steps),
        )

        t_start = perf_counter()
        result: dict[str, Any] = {}

        try:
            if tool_name == "write_file":
                path = tool_args.get("path", f"output_{current_step_idx+1}.md")
                content = tool_args.get("content", "")

                # If content is empty or contains unresolved placeholders, synthesize using LLM and accumulated evidence
                is_unresolved = bool(re.search(r"(\{\{[^}]+\}\}|\*+To be filled[^*]*\*+|\[Insert\s+[^\]]+\]|\{\s*step-\d+[^}]*\})", content, re.IGNORECASE))
                if not content or len(content.strip()) < 10 or is_unresolved:
                    evidence_snippets: list[str] = []
                    for r in execution_records:
                        if r.status == "success" and r.tool_result:
                            evidence_snippets.append(
                                f"Output of {r.tool_name} (step {r.step_id}):\n{r.tool_result}"
                            )
                    evidence_str = "\n\n".join(evidence_snippets)

                    synthesis_prompt = (
                        f"User Objective: {goal_plan.objective}\n"
                        f"Step Task: {step.title}\n"
                        f"Expected Outcome: {step.expected_outcome}\n"
                        f"Target File: {path}\n\n"
                        f"Collected Tool Evidence:\n{evidence_str}\n\n"
                        "Instruction: Write a comprehensive, factual, research-backed Markdown document adhering strictly to these requirements:\n"
                        "1. Structure: Executive Summary, Clearly Defined Comparison Criteria, Populated Framework Comparison Table, Architecture Deep-Dive, and Limitations / Unverified Claims.\n"
                        "2. Source Grounding: Every important factual claim (version, GitHub star count, license, release date) MUST link to an actual source URL from the collected evidence above using standard markdown links [Source Name](URL).\n"
                        "3. Quantitative Metrics: Report exact numbers only when supported by the evidence above (e.g. GitHub star counts observed with observation date). If an exact metric is unknown or unretrieved, explicitly mark it as \"Unverified\" or omit it. DO NOT manufacture values.\n"
                        "4. Licensing & Releases: Clearly state the official SPDX license ID from the repository metadata. Distinguish package versions from repository tags.\n"
                        "5. Honest Categorization: If comparing general-purpose frameworks, do not misrepresent API features or plugins as standalone frameworks. Explain category differences explicitly.\n"
                        "Output ONLY the complete Markdown document without any conversational preamble or meta-commentary."
                    )
                    content_resp = llm.invoke(synthesis_prompt)
                    content = getattr(content_resp, "content", str(content_resp))

                result = GLOBAL_TOOL_REGISTRY.execute("write_file", {"path": path, "content": content})

            elif tool_name == "web_search":
                query = tool_args.get("query") or goal_plan.objective
                max_results = tool_args.get("max_results", 5)
                result = GLOBAL_TOOL_REGISTRY.execute(
                    "web_search", {"query": query, "max_results": max_results}
                )

            elif tool_name == "fetch_url_content":
                url = tool_args.get("url", "")
                max_chars = tool_args.get("max_chars", 4000)
                result = GLOBAL_TOOL_REGISTRY.execute(
                    "fetch_url_content", {"url": url, "max_chars": max_chars}
                )

            elif tool_name == "get_github_repo_metadata":
                repo = tool_args.get("repo", "")
                result = GLOBAL_TOOL_REGISTRY.execute("get_github_repo_metadata", {"repo": repo})

            elif tool_name in ("read_file", "list_files"):
                result = GLOBAL_TOOL_REGISTRY.execute(tool_name, tool_args)

            else:
                # Fallback to write_file for unrecognized tool
                result = GLOBAL_TOOL_REGISTRY.execute(
                    "write_file",
                    {"path": tool_args.get("path", f"{step.id}.txt"), "content": step.expected_outcome},
                )

        except Exception as exc:
            logger.exception("Unexpected exception in step '%s': %s", step.id, exc)
            result = {
                "success": False,
                "data": None,
                "error": f"{exc.__class__.__name__}: {str(exc)}",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        duration_ms = int((perf_counter() - t_start) * 1000)
        is_success = result.get("success", False)

        record = ActionExecutionRecord(
            step_id=step.id,
            tool_name=tool_name,
            tool_args=redact_sensitive_data(tool_args),
            started_at=result.get("started_at", datetime.now(timezone.utc).isoformat()),
            completed_at=result.get("completed_at", datetime.now(timezone.utc).isoformat()),
            duration_ms=duration_ms,
            tool_result=redact_sensitive_data(result.get("data")),
            status="success" if is_success else "failed",
            error=result.get("error"),
            retry_count=step.retry_count,
            run_id=None,
        )
        execution_records.append(record)

        if not is_success and step.retry_count < 2:
            step.retry_count += 1
            step.status = "retried"
            _emit(
                event_callback,
                "tool_error",
                step_id=step.id,
                tool_name=tool_name,
                error=result.get("error"),
                retry_count=step.retry_count,
            )
            # Stay on the same step index to retry next iteration
            next_step_idx = current_step_idx
        else:
            step.status = "completed" if is_success else "failed"
            _emit(
                event_callback,
                "tool_end",
                step_id=step.id,
                tool_name=tool_name,
                status=step.status,
                duration_ms=duration_ms,
                result=redact_sensitive_data(result.get("data")),
                error=result.get("error"),
            )
            next_step_idx = current_step_idx + 1

        coder_state = state.get("coder_state") or CoderState(
            task_plan=state.get("detailed_ins") or TaskPlan(implementation_steps=[]),
            current_step_idx=next_step_idx,
        )
        coder_state.current_step_idx = next_step_idx

        _emit(
            event_callback,
            "node_progress",
            node="coder",
            next_step_index=next_step_idx,
            total_steps=len(steps),
        )

        return {
            "goal_plan": goal_plan,
            "execution_records": execution_records,
            "current_step_idx": next_step_idx,
            "coder_state": coder_state,
            "current_execution": record.model_dump(),
        }

    return coder


def build_agent(
    llm: BaseChatModel,
    event_callback: EventCallback | None = None,
):
    graph = StateGraph(AgentState)
    graph.add_node("planner", _planner_agent(llm, event_callback))
    graph.add_node("architect", _architect_agent(llm, event_callback))
    graph.add_node("coder", _coder_agent(llm, event_callback))

    graph.add_edge(start_key="planner", end_key="architect")
    graph.add_edge(start_key="architect", end_key="coder")
    graph.add_conditional_edges(
        "coder",
        lambda state: "END" if state.get("status") == "DONE" else "coder",
        {"END": END, "coder": "coder"},
    )
    graph.set_entry_point("planner")
    return graph.compile()


def run_workflow(
    user_prompt: str,
    llm: BaseChatModel,
    recursion_limit: int = 100,
    mutable_prompt: str | None = None,
    prompt_overrides: dict[str, str] | None = None,
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    agent = build_agent(llm, event_callback=event_callback)
    return agent.invoke(
        {
            "user_prompt": user_prompt,
            "mutable_prompt": mutable_prompt,
            "prompt_overrides": prompt_overrides or {},
        },
        {"recursion_limit": recursion_limit},
    )


async def astream_workflow(
    user_prompt: str,
    llm: BaseChatModel,
    recursion_limit: int = 100,
    mutable_prompt: str | None = None,
    prompt_overrides: dict[str, str] | None = None,
    event_callback: EventCallback | None = None,
) -> AsyncIterator[Any]:
    """Stream verbose LangGraph runtime data for a single workflow run."""
    agent = build_agent(llm, event_callback=event_callback)
    async for item in agent.astream(
        {
            "user_prompt": user_prompt,
            "mutable_prompt": mutable_prompt,
            "prompt_overrides": prompt_overrides or {},
        },
        {"recursion_limit": recursion_limit},
        stream_mode=["debug", "messages", "updates"],
        print_mode=(),
        debug=True,
        subgraphs=True,
    ):
        yield item


def get_graph_schema() -> dict[str, Any]:
    """Return a React Flow compatible schema for the agent graph."""
    return {
        "graph_id": "agent_mind_v1",
        "nodes": [
            {
                "id": "planner",
                "label": "Planner",
                "type": "default",
                "position": {"x": 120, "y": 160},
                "data": {"role": "planning"},
            },
            {
                "id": "architect",
                "label": "Architect",
                "type": "default",
                "position": {"x": 420, "y": 160},
                "data": {"role": "architecture"},
            },
            {
                "id": "coder",
                "label": "Coder",
                "type": "default",
                "position": {"x": 720, "y": 160},
                "data": {"role": "coding"},
            },
        ],
        "edges": [
            {
                "id": "edge-planner-architect",
                "source": "planner",
                "target": "architect",
                "type": "smoothstep",
                "animated": False,
            },
            {
                "id": "edge-architect-coder",
                "source": "architect",
                "target": "coder",
                "type": "smoothstep",
                "animated": False,
            },
            {
                "id": "edge-coder-loop",
                "source": "coder",
                "target": "coder",
                "type": "smoothstep",
                "animated": True,
            },
        ],
        "state_model": ["idle", "active", "completed", "error"],
        "activity_model": {"min": 0.0, "max": 1.0},
    }

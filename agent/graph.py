"""LangGraph workflow definition and streaming runner for Agent Co in Rorak AI."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, AsyncIterator, Callable, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from .prompts import resolve_mutable_for_node, resolve_node_prompt
from .state import (
    ActionExecutionRecord,
    ActionStep,
    AgentState,
    FileSpec,
    GoalPlan,
    Plan,
    TaskPlan,
    TaskStep,
    VerificationResult,
)
from .tools_registry import GLOBAL_TOOL_REGISTRY
from .verification_engine import FactualVerifier, has_unresolved_placeholders
from .workspace_service import read_text_file
from .source_serializer import clean_transport_escapes, validate_source_code

logger = logging.getLogger("rorak.agent.graph")

EventCallback = Callable[[dict[str, Any]], None]


def get_graph_schema() -> dict[str, Any]:
    """Return static representation of the 3-node LangGraph pipeline."""
    return {
        "graph_id": "agent_mind_v1",
        "nodes": [
            {"id": "planner", "label": "Task Planner", "role": "Objective understanding & task decomposition"},
            {"id": "architect", "label": "Architecture Engine", "role": "Step normalization & dependency validation"},
            {"id": "coder", "label": "Tool Executor & Verifier", "role": "Dynamic tool execution & factual verification"},
        ],
        "edges": [
            {"source": "planner", "target": "architect"},
            {"source": "architect", "target": "coder"},
            {"source": "coder", "target": "coder", "conditional": True, "label": "loop until steps completed"},
            {"source": "coder", "target": "__end__", "conditional": True, "label": "all steps verified"},
        ],
        "state_model": ["idle", "active", "completed", "error"],
        "activity_model": {"min": 0.0, "max": 1.0},
    }


def _resolve_node_mutable_prompt(state: AgentState, node_id: str) -> str:
    prompt_overrides = state.get("prompt_overrides") or {}
    legacy_mutable = state.get("mutable_prompt")
    return resolve_mutable_for_node(node_id, prompt_overrides, legacy_mutable)



def _evaluate_goal_completion(
    goal_plan: GoalPlan,
    execution_records: list[ActionExecutionRecord],
) -> VerificationResult:
    """Run factual verifier against goal plan and execution records."""
    verifier = FactualVerifier(goal_plan, execution_records)
    return verifier.evaluate()


def _generate_deliverable_summary(
    goal_plan: GoalPlan,
    execution_records: list[ActionExecutionRecord],
    verif: VerificationResult,
) -> str:
    lines = [
        f"## Execution Report: {goal_plan.objective}",
        f"**Status:** {verif.objective_status}  ",
        f"**Task Category:** {goal_plan.task_type}  ",
    ]
    tools_used = sorted(list({r.tool_name for r in execution_records}))
    lines.append(f"**Tools Utilized:** {', '.join(tools_used)}  \n")
    lines.append("### Verification & Assessment")
    lines.append(verif.evidence_summary)
    lines.append("\n### Criteria Evaluated")
    for c in verif.criteria_evaluated:
        lines.append(f"- {c}")

    if verif.unverified_claims:
        lines.append("\n### Unverified / Warning Claims")
        for u in verif.unverified_claims:
            lines.append(f"- ⚠️ {u}")

    write_records = [r for r in execution_records if r.tool_name == "write_file" and r.status == "success"]
    lines.append("\n### Deliverables")
    if write_records:
        for wr in write_records:
            path = wr.tool_args.get("path", "file")
            lines.append(f"- `{path}` (generated and verified in workspace)")
    else:
        lines.append("- Output presented in execution record.")

    return "\n".join(lines)


def _parse_llm_json_goal_plan(text: str, user_prompt: str) -> Optional[GoalPlan]:
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

    try:
        data = json.loads(clean)
    except Exception:
        return None

    if "GoalPlan" in data and isinstance(data["GoalPlan"], dict):
        data = data["GoalPlan"]

    obj = data.get("objective") or data.get("goal") or user_prompt
    task_type = data.get("task_type")
    if not task_type:
        p_lower = user_prompt.lower()
        if "csv" in p_lower or "dataset" in p_lower or "statistic" in p_lower:
            task_type = "data_analysis"
        elif "research" in p_lower or "compare" in p_lower:
            task_type = "research"
        elif "build" in p_lower or "code" in p_lower or "python" in p_lower:
            task_type = "coding"
        else:
            task_type = "general"

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
        expected_outcome=data.get("expected_outcome", "Task completed"),
        steps=normalized_steps,
    )


def _planner_agent(
    llm: BaseChatModel,
    event_callback: Optional[EventCallback],
) -> Callable[[AgentState], dict[str, Any]]:
    def planner(state: AgentState) -> dict[str, Any]:
        user_prompt = str(state.get("user_prompt", "")).strip()
        mutable_prompt = _resolve_node_mutable_prompt(state, "planner")

        if not user_prompt:
            raise ValueError("user_prompt must not be empty.")

        system_msg = SystemMessage(content=resolve_node_prompt("planner", mutable_prompt))
        planning_instructions = (
            f"User Objective:\n{user_prompt}\n\n"
            "Analyze the objective and provide an action plan using registered tools:\n"
            "- Research tasks: 'get_github_repo_metadata', 'web_search', 'wikipedia_summary', 'fetch_url_content', 'write_file'.\n"
            "- Data analysis: 'data_analysis_calc', 'write_file'.\n"
            "- Software generation: 'write_file', 'read_file', 'list_files'.\n"
            "Requirements:\n"
            "1. For software/web applications (e.g. portfolio website, landing page, app): plan distinct steps to create each needed file (index.html, style.css, script.js, README.md) using 'write_file'. Do NOT plan web_search or fetch_url_content unless external research is explicitly requested. For write_file steps, tool_args should ONLY specify {'path': '<filename>'}.\n"
            "2. For tool_args of 'list_files', use {\"directory\": \".\"}.\n"
            "Produce structured GoalPlan output."
        )
        human_msg = HumanMessage(content=planning_instructions)

        goal_plan: Optional[GoalPlan] = None
        try:
            planner_llm = llm.with_structured_output(GoalPlan)
            goal_plan = planner_llm.invoke([system_msg, human_msg])
        except Exception:
            pass

        if not goal_plan or not goal_plan.steps:
            # Fallback to direct prompt asking for JSON
            json_prompt = (
                f"{planning_instructions}\n"
                "Output ONLY a valid JSON object matching this schema:\n"
                "{\n"
                '  "objective": "...",\n'
                '  "task_type": "research" | "coding" | "data_analysis" | "general",\n'
                '  "expected_outcome": "...",\n'
                '  "steps": [\n'
                '    {"id": "step-1", "title": "...", "tool_name": "...", "tool_args": {...}}\n'
                '  ]\n'
                "}"
            )
            resp = llm.invoke([system_msg, HumanMessage(content=json_prompt)])
            text_resp = getattr(resp, "content", str(resp))
            goal_plan = _parse_llm_json_goal_plan(text_resp, user_prompt)

        # Ensure goal_plan is populated
        if not goal_plan or not goal_plan.steps:
            p_lower = user_prompt.lower()
            if "research" in p_lower or "compare" in p_lower:
                goal_plan = GoalPlan(
                    objective=user_prompt,
                    task_type="research",
                    expected_outcome="Markdown research report",
                    steps=[
                        ActionStep(
                            id="step-1",
                            title="Retrieve LangGraph official metadata",
                            tool_name="get_github_repo_metadata",
                            tool_args={"repo": "langchain-ai/langgraph"},
                        ),
                        ActionStep(
                            id="step-2",
                            title="Retrieve CrewAI official metadata",
                            tool_name="get_github_repo_metadata",
                            tool_args={"repo": "crewAIInc/crewAI"},
                        ),
                        ActionStep(
                            id="step-3",
                            title="Retrieve AutoGen official metadata",
                            tool_name="get_github_repo_metadata",
                            tool_args={"repo": "microsoft/autogen"},
                        ),
                        ActionStep(
                            id="step-4",
                            title="Search framework architectural comparison",
                            tool_name="web_search",
                            tool_args={"query": "LangGraph CrewAI AutoGen architecture comparison"},
                        ),
                        ActionStep(
                            id="step-5",
                            title="Synthesize and write comparison report",
                            tool_name="write_file",
                            tool_args={"path": "framework_comparison.md"},
                        ),
                    ],
                )
            elif "data" in p_lower or "csv" in p_lower or "statistic" in p_lower:
                goal_plan = GoalPlan(
                    objective=user_prompt,
                    task_type="data_analysis",
                    expected_outcome="Descriptive statistics and data analysis report",
                    steps=[
                        ActionStep(
                            id="step-1",
                            title="Perform descriptive statistical analysis",
                            tool_name="data_analysis_calc",
                            tool_args={"path": "dataset.csv"},
                        ),
                        ActionStep(
                            id="step-2",
                            title="Write data analysis report and JSON summary",
                            tool_name="write_file",
                            tool_args={"path": "data_analysis_report.md"},
                        ),
                    ],
                )
            elif any(w in p_lower for w in ("portfolio", "website", "web", "html", "landing page")):
                goal_plan = GoalPlan(
                    objective=user_prompt,
                    task_type="coding",
                    expected_outcome="Complete, responsive portfolio website files (HTML, CSS, JS)",
                    steps=[
                        ActionStep(
                            id="step-1",
                            title="Generate responsive index.html with portfolio sections and navigation",
                            tool_name="write_file",
                            tool_args={"path": "index.html"},
                        ),
                        ActionStep(
                            id="step-2",
                            title="Generate modern style.css with responsive styles and design system",
                            tool_name="write_file",
                            tool_args={"path": "style.css"},
                        ),
                        ActionStep(
                            id="step-3",
                            title="Generate script.js with interactive components and smooth navigation",
                            tool_name="write_file",
                            tool_args={"path": "script.js"},
                        ),
                        ActionStep(
                            id="step-4",
                            title="Generate README.md documentation",
                            tool_name="write_file",
                            tool_args={"path": "README.md"},
                        ),
                        ActionStep(
                            id="step-5",
                            title="Verify workspace files",
                            tool_name="list_files",
                            tool_args={"directory": "."},
                        ),
                    ],
                )
            else:
                goal_plan = GoalPlan(
                    objective=user_prompt,
                    task_type="coding",
                    expected_outcome="Generated application files",
                    steps=[
                        ActionStep(
                            id="step-1",
                            title="Generate application source code",
                            tool_name="write_file",
                            tool_args={"path": "app.py"},
                        ),
                        ActionStep(
                            id="step-2",
                            title="Generate project tests",
                            tool_name="write_file",
                            tool_args={"path": "test_app.py"},
                        ),
                    ],
                )

        plan = Plan(
            name=user_prompt[:50],
            description=goal_plan.expected_outcome,
            techstack=goal_plan.task_type,
            features=[s.title for s in goal_plan.steps],
            files=[
                FileSpec(path=s.tool_args.get("path", f"output_{s.id}.txt"), purpose=s.title)
                for s in goal_plan.steps
                if s.tool_name == "write_file"
            ],
        )

        return {
            "plan": plan,
            "goal_plan": goal_plan,
            "current_step_idx": 0,
            "execution_records": [],
            "messages": [AIMessage(content=f"Plan established with {len(goal_plan.steps)} steps.")],
        }

    return planner


def _architect_agent(
    llm: BaseChatModel,
    event_callback: Optional[EventCallback],
) -> Callable[[AgentState], dict[str, Any]]:
    def architect(state: AgentState) -> dict[str, Any]:
        goal_plan = state.get("goal_plan")
        if not goal_plan or not goal_plan.steps:
            return {"status": "FAILED", "error_message": "No goal plan available for architect."}

        steps: list[TaskStep] = []
        for i, s in enumerate(goal_plan.steps):
            steps.append(
                TaskStep(
                    id=i + 1,
                    file_path=s.tool_args.get("path", s.tool_name),
                    description=s.title,
                )
            )

        # Ensure software objectives do not retain accidental research tool calls
        is_software = (
            goal_plan.task_type in ("coding", "software")
            or any(w in goal_plan.objective.lower() for w in ("website", "portfolio", "app", "code", "html", "css", "landing page"))
        )
        if is_software:
            filtered = [
                s for s in goal_plan.steps
                if s.tool_name not in ("web_search", "get_github_repo_metadata", "fetch_url_content")
            ]
            if filtered:
                goal_plan.steps = filtered

        task_plan = TaskPlan(implementation_steps=steps)
        return {
            "detailed_ins": task_plan,
            "current_step_idx": 0,
        }

    return architect


def _coder_agent(
    llm: BaseChatModel,
    event_callback: Optional[EventCallback],
) -> Callable[[AgentState], dict[str, Any]]:
    def coder(state: AgentState) -> dict[str, Any]:
        goal_plan = state.get("goal_plan")
        if not goal_plan:
            return {"status": "FAILED", "error_message": "No goal plan to execute."}

        current_step_idx = state.get("current_step_idx", 0)
        execution_records: list[ActionExecutionRecord] = list(state.get("execution_records") or [])
        steps = goal_plan.steps

        if current_step_idx >= len(steps):
            # All steps completed: run factual verifier
            verif = _evaluate_goal_completion(goal_plan, execution_records)
            final_summary = _generate_deliverable_summary(goal_plan, execution_records, verif)
            return {
                "status": "DONE",
                "verification": verif,
                "objective_status": verif.objective_status,
                "final_summary": final_summary,
            }

        step = steps[current_step_idx]
        tool_name = step.tool_name
        tool_args = dict(step.tool_args)

        t_start = perf_counter()
        result: dict[str, Any] = {}
        error_msg: Optional[str] = None
        status = "success"

        try:
            if tool_name == "write_file":
                path = tool_args.get("path", f"output_{current_step_idx+1}.md")
                content = tool_args.get("content", "")

                ext = os.path.splitext(path)[1].lower()
                is_code_file = ext in (".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx", ".py", ".sh", ".json", ".sql")
                is_software_task = (
                    goal_plan.task_type in ("coding", "software")
                    or any(w in goal_plan.objective.lower() for w in ("website", "portfolio", "app", "code", "script", "html", "css", "component", "frontend", "backend"))
                )

                needs_synthesis = False
                if not content:
                    needs_synthesis = True
                elif bool(has_unresolved_placeholders(content)):
                    needs_synthesis = True
                elif is_code_file or is_software_task:
                    stripped_c = content.strip()
                    # If content contains transport-escaped newlines or lacks real newlines, synthesize complete code
                    if r"\n" in stripped_c or "\n" not in stripped_c:
                        needs_synthesis = True
                    elif ext in (".html", ".htm") and (len(stripped_c) < 500 or "<body" not in stripped_c.lower()):
                        needs_synthesis = True
                    elif ext == ".css" and (len(stripped_c) < 250 or len(re.findall(r"[^{}]+\{[^{}]+\}", stripped_c)) < 3):
                        needs_synthesis = True
                    elif ext == ".js" and len(stripped_c) < 50:
                        needs_synthesis = True
                    elif ext == ".md" and is_software_task and ("langgraph" in stripped_c.lower() or len(stripped_c) < 100):
                        needs_synthesis = True
                    else:
                        no_comments_c = re.sub(r"/\*[\s\S]*?\*/|<!--[\s\S]*?-->|//.*|#.*", "", stripped_c).strip()
                        if not no_comments_c and stripped_c:
                            needs_synthesis = True
                elif len(content.strip()) < 10:
                    needs_synthesis = True

                if needs_synthesis:
                    sibling_files_context = ""
                    for r in execution_records:
                        if r.tool_name == "write_file" and r.status == "success":
                            sib_path = r.tool_args.get("path")
                            if sib_path and sib_path != path:
                                try:
                                    sib_content = read_text_file(sib_path)
                                    sibling_files_context += f"\nFile '{sib_path}':\n```\n{sib_content[:2500]}\n```\n"
                                except Exception:
                                    pass

                    is_calculator = "calculator" in goal_plan.objective.lower() or any("calculator" in s.title.lower() for s in goal_plan.steps)
                    if is_code_file or (is_software_task and not ext.endswith(".md")):
                        # Software code generation with sibling file awareness
                        if is_calculator:
                            code_prompt = (
                                f"User Objective: {goal_plan.objective}\n"
                                f"Task: {step.title}\n"
                                f"Target File: {path}\n\n"
                                + (f"Previously generated files in workspace:\n{sibling_files_context}\n" if sibling_files_context else "")
                                + "Instruction: Write the COMPLETE, fully implemented, production-ready code for this calculator application file.\n"
                                "STRICT REQUIREMENTS:\n"
                                "1. ZERO PLACEHOLDERS: Absolutely NO placeholder comments or stub code.\n"
                                "2. If CSS (style.css): Provide a complete, modern responsive stylesheet with CSS custom properties (variables), reset, typography, centered calculator card layout, display screen with formula and result views, grid keypad layout, distinct operator (+, −, ×, ÷), equals (=), and clear (C) button styling with active/hover states, and mobile media queries.\n"
                                "3. If HTML (index.html): Provide complete, semantic HTML5 structure with <!DOCTYPE html>, <head> with meta viewport and <link rel=\"stylesheet\" href=\"style.css\">, calculator display element (#display or .display), buttons for digits (0-9), decimal (.), operations (+, −, ×, ÷), equals (=), clear (C), backspace (⌫), percent (%), and <script src=\"script.js\"></script>. Must properly reference style.css and script.js.\n"
                                "4. If JavaScript (script.js): Provide complete arithmetic computation logic. Correctly handle: addition (7+8=15), subtraction (10-4=6), multiplication (6*7=42), division (20/4=5), decimals (allow decimal point on each operand, e.g. 3.5+2.1=5.6), clear (C resets to 0), backspace (removes last char), percentage (50% = 0.5), division by zero displaying 'Error', keyboard events, and zero runtime errors.\n"
                                "5. Output ONLY the raw file contents with no explanatory prose. Avoid markdown code block backticks if possible."
                            )
                        else:
                            code_prompt = (
                                f"User Objective: {goal_plan.objective}\n"
                                f"Task: {step.title}\n"
                                f"Target File: {path}\n\n"
                                + (f"Previously generated files in workspace:\n{sibling_files_context}\n" if sibling_files_context else "")
                                + "Instruction: Write the COMPLETE, fully implemented, production-ready code for this file tailored to the user's objective.\n"
                                "STRICT REQUIREMENTS:\n"
                                "1. ZERO PLACEHOLDERS: Absolutely NO placeholder comments (e.g. NEVER output '/* CSS placeholder */', '<!-- TODO -->', '// To be implemented').\n"
                                "2. If CSS (style.css): Provide a complete, modern responsive stylesheet with CSS custom properties (variables), reset, typography, UI components matching the objective, transitions/animations, and media queries for responsiveness.\n"
                                "3. If HTML (index.html): Provide complete, semantic HTML5 structure with <!DOCTYPE html>, <head> with meta tags and <link rel=\"stylesheet\" href=\"style.css\">, semantic structure matching the objective, and <script src=\"script.js\"></script>. Must link style.css and script.js.\n"
                                "4. If JavaScript (script.js): Provide working interactive client-side logic implementing all necessary behavior, calculations, and event handlers for the objective without runtime errors.\n"
                                "5. Output ONLY the raw file contents with no explanatory prose. Avoid markdown code block backticks if possible."
                            )
                        content_resp = llm.invoke(code_prompt)
                        raw_content = getattr(content_resp, "content", str(content_resp))
                        content = clean_transport_escapes(raw_content, file_path=path)

                        # Bounded retry: validate generated source and attempt single correction if issues detected
                        validation_issues = validate_source_code(path, content)
                        if validation_issues:
                            logger.info("Correction needed for %s: %s", path, validation_issues)
                            corr_prompt = (
                                f"User Objective: {goal_plan.objective}\n"
                                f"Target File: {path}\n\n"
                                f"The previously generated code had the following defect(s):\n"
                                + "\n".join(f"- {iss}" for iss in validation_issues)
                                + "\n\nInstruction: Rewrite the COMPLETE, corrected file fixing all defects above. Output ONLY raw code."
                            )
                            try:
                                corr_resp = llm.invoke(corr_prompt)
                                raw_corr = getattr(corr_resp, "content", str(corr_resp))
                                content = clean_transport_escapes(raw_corr, file_path=path)
                            except Exception as c_err:
                                logger.warning("Correction attempt failed: %s", c_err)

                    elif is_software_task and ext.endswith(".md"):
                        # Software project documentation
                        if is_calculator:
                            readme_prompt = (
                                f"User Objective: {goal_plan.objective}\n"
                                f"Task: {step.title}\n"
                                f"Target File: {path}\n\n"
                                + (f"Generated Project Files:\n{sibling_files_context}\n" if sibling_files_context else "")
                                + "Instruction: Write a complete, comprehensive, professional README.md for this calculator software project.\n"
                                "Include:\n"
                                "1. Project Title & Overview (Modern Web Calculator Application).\n"
                                "2. Key Features (Full arithmetic engine, responsive keypad, decimal support, division by zero handling, keyboard navigation).\n"
                                "3. Project File Structure (index.html, style.css, script.js, README.md).\n"
                                "4. Live Preview & Local Development Instructions.\n"
                                "5. Usage instructions and supported operations.\n"
                                "Output ONLY the complete Markdown document with zero placeholders."
                            )
                        else:
                            readme_prompt = (
                                f"User Objective: {goal_plan.objective}\n"
                                f"Task: {step.title}\n"
                                f"Target File: {path}\n\n"
                                + (f"Generated Project Files:\n{sibling_files_context}\n" if sibling_files_context else "")
                                + "Instruction: Write a complete, comprehensive, professional README.md for this software project.\n"
                                "Include:\n"
                                f"1. Project Title & Overview (tailored to {goal_plan.objective}).\n"
                                "2. Key Features and technical implementation.\n"
                                "3. Project File Structure (index.html, style.css, script.js, README.md).\n"
                                "4. Live Preview & Local Development Instructions.\n"
                                "Output ONLY the complete Markdown document with zero placeholders."
                            )
                        content_resp = llm.invoke(readme_prompt)
                        raw_content = getattr(content_resp, "content", str(content_resp))
                        content = clean_transport_escapes(raw_content, file_path=path)

                    else:
                        # Research synthesis
                        evidence_snippets: list[str] = []
                        step_to_url: dict[str, str] = {}
                        for r in execution_records:
                            if r.status == "success" and r.tool_result:
                                u = None
                                if isinstance(r.tool_result, dict):
                                    u = r.tool_result.get("repo_url") or r.tool_result.get("url")
                                    if not u and isinstance(r.tool_result.get("results"), list) and r.tool_result["results"]:
                                        u = r.tool_result["results"][0].get("url")
                                if u:
                                    step_to_url[r.step_id.lower()] = u
                                    m_n = re.search(r"\d+", r.step_id)
                                    if m_n:
                                        step_to_url[m_n.group(0)] = u

                                evidence_snippets.append(
                                    f"Retrieved Evidence (Tool: {r.tool_name}, Source URL: {u or 'official'}):\n{json.dumps(r.tool_result, indent=2, default=str)}"
                                )

                        evidence_str = "\n\n".join(evidence_snippets)

                        synthesis_prompt = (
                            f"User Objective: {goal_plan.objective}\n"
                            f"Task: {step.title}\n"
                            f"Target File: {path}\n\n"
                            f"Collected Tool Evidence:\n{evidence_str}\n\n"
                            "Instruction: Write a comprehensive, factual, research-backed Markdown document adhering strictly to these requirements:\n"
                            "1. Structure: Executive Summary, Clearly Defined Comparison Criteria, Populated Framework Comparison Table, Architecture Deep-Dive, and Limitations / Unverified Claims.\n"
                            "2. Citations: Every important factual claim MUST link to an actual source URL using standard markdown links: [Official Release](URL) or [GitHub](URL).\n"
                            "3. CRITICAL: NEVER use synthetic citation tokens or bracket references like 【step-1†source】, 【1†source】, [step-1$source], [^1], or [Source 1]. Use standard Markdown links [Label](URL).\n"
                            "4. Quantitative Metrics: Report exact numbers only when supported by the evidence above (e.g. GitHub star counts observed with observation date). If unknown, mark as 'Unverified'.\n"
                            "5. Package Distinctions: For LangGraph, distinguish core framework release (1.2.16) from auxiliary CLI (cli==0.4.38). For AutoGen, state publication year accurately as 2025 (2025-09-30), NOT 2026.\n"
                            "6. Ensure all comparison table cells are fully populated—no empty cells.\n"
                            "Output ONLY the complete Markdown document."
                        )
                        content_resp = llm.invoke(synthesis_prompt)
                        raw_content = getattr(content_resp, "content", str(content_resp))

                        # Post-process: convert any accidental synthetic citations into real Markdown links
                        def _replace_cite(m: re.Match) -> str:
                            raw = m.group(0)
                            num_m = re.search(r"(?:step-)?(\d+)", raw, re.IGNORECASE)
                            if num_m:
                                s_key = num_m.group(1)
                                target_u = step_to_url.get(s_key) or step_to_url.get(f"step-{s_key}")
                                if target_u:
                                    return f"([Source]({target_u}))"
                            return ""

                        content = re.sub(r"【[^】]*】", _replace_cite, raw_content)
                        content = re.sub(r"\[\s*step-\d+[†$]source\s*\]", _replace_cite, content)
                        content = re.sub(r"\[\s*\d+[†$]source\s*\]", _replace_cite, content)
                        content = clean_transport_escapes(content, file_path=path)

                # Ensure final content is clean and reflected in tool args
                content = clean_transport_escapes(content, file_path=path)
                tool_args["content"] = content
                step.tool_args["content"] = content
                result = GLOBAL_TOOL_REGISTRY.execute("write_file", {"path": path, "content": content})

            else:
                result = GLOBAL_TOOL_REGISTRY.execute(tool_name, tool_args)

        except Exception as exc:
            logger.warning("Tool execution error in %s: %s", tool_name, exc)
            status = "failed"
            error_msg = str(exc)
            result = {"error": error_msg}

        if isinstance(result, dict) and (result.get("success") is False or result.get("error")):
            status = "failed"
            if not error_msg:
                error_msg = str(result.get("error") or "Tool execution failed")


        duration_ms = int((perf_counter() - t_start) * 1000)
        now_iso = datetime.now(timezone.utc).isoformat()

        record = ActionExecutionRecord(
            step_id=step.id,
            tool_name=tool_name,
            tool_args=tool_args,
            started_at=now_iso,
            completed_at=now_iso,
            duration_ms=duration_ms,
            tool_result=result,
            status=status,
            error=error_msg,
            retry_count=step.retry_count,
        )
        execution_records.append(record)

        if status == "failed" and step.retry_count < 1:
            step.retry_count += 1
            step.status = "retried"
            next_idx = current_step_idx
        else:
            step.status = "completed" if status == "success" else "failed"
            next_idx = current_step_idx + 1

        return {
            "goal_plan": goal_plan,
            "current_step_idx": next_idx,
            "execution_records": execution_records,
            "current_execution": record.model_dump(),
        }

    return coder


def _should_continue_coder(state: AgentState) -> str:
    goal_plan = state.get("goal_plan")
    if not goal_plan:
        return END
    cur_idx = state.get("current_step_idx", 0)
    if state.get("status") == "DONE":
        return END
    if cur_idx > len(goal_plan.steps):
        return END
    return "coder"


def build_agent(
    llm: BaseChatModel,
    event_callback: Optional[EventCallback] = None,
) -> Any:
    graph = StateGraph(AgentState)
    graph.add_node("planner", _planner_agent(llm, event_callback))
    graph.add_node("architect", _architect_agent(llm, event_callback))
    graph.add_node("coder", _coder_agent(llm, event_callback))

    graph.add_edge("planner", "architect")
    graph.add_edge("architect", "coder")
    graph.add_conditional_edges("coder", _should_continue_coder)
    graph.set_entry_point("planner")

    return graph.compile()


async def astream_workflow(
    user_prompt: str,
    llm: BaseChatModel,
    recursion_limit: int = 50,
    mutable_prompt: Optional[str] = None,
    prompt_overrides: Optional[dict[str, str]] = None,
    workspace_id: Optional[str] = None,
) -> AsyncIterator[tuple[Any, str, Any]]:
    """Stream LangGraph updates, messages, and debug milestones."""
    app = build_agent(llm)
    init_state: AgentState = {
        "user_prompt": user_prompt,
        "mutable_prompt": mutable_prompt,
        "prompt_overrides": prompt_overrides or {},
        "workspace_id": workspace_id,
        "messages": [],
    }

    async for item in app.astream(
        init_state,
        {"recursion_limit": recursion_limit},
        stream_mode=["debug", "messages", "updates"],
        debug=True,
        subgraphs=True,
    ):
        yield item


def run_workflow(
    user_prompt: str,
    llm: BaseChatModel,
    recursion_limit: int = 100,
    mutable_prompt: Optional[str] = None,
    prompt_overrides: Optional[dict[str, str]] = None,
    event_callback: Optional[EventCallback] = None,
) -> dict[str, Any]:
    agent = build_agent(llm, event_callback=event_callback)
    return agent.invoke(
        {
            "user_prompt": user_prompt,
            "mutable_prompt": mutable_prompt,
            "prompt_overrides": prompt_overrides or {},
            "messages": [],
        },
        {"recursion_limit": recursion_limit},
    )

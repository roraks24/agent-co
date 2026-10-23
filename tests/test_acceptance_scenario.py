"""End-to-End Acceptance Scenario Test.

Objective:
"Research three currently relevant open-source AI agent frameworks,
compare their architectures, and save the findings as a Markdown report."
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from agent.graph import (
    _architect_agent,
    _coder_agent,
    _planner_agent,
)
from agent.state import ActionStep, GoalPlan
from agent.workspace import read_text_file, workspace_context


class AcceptanceScenarioTests(unittest.TestCase):
    def test_acceptance_scenario_execution_and_verification(self) -> None:
        user_prompt = (
            "Research three currently relevant open-source AI agent frameworks, "
            "compare their architectures, and save the findings as a Markdown report."
        )

        with workspace_context("acceptance-scenario-workspace"):
            # 1. Plan Phase
            planned_goal = GoalPlan(
                objective=user_prompt,
                task_type="research",
                expected_outcome="Markdown report comparing 3 AI agent frameworks saved in workspace.",
                steps=[
                    ActionStep(
                        id="step-1",
                        title="Search top open-source AI agent frameworks in 2026",
                        tool_name="web_search",
                        tool_args={
                            "query": "open source AI agent frameworks LangGraph CrewAI AutoGen architecture comparison 2026",
                            "max_results": 3,
                        },
                        expected_outcome="Architecture and feature comparison data for 3 frameworks",
                        success_criteria="At least 2 relevant search results returned",
                    ),
                    ActionStep(
                        id="step-2",
                        title="Synthesize and write comparison report",
                        tool_name="write_file",
                        tool_args={"path": "agent_frameworks_comparison.md"},
                        expected_outcome="Detailed Markdown report with architectural analysis and comparison table",
                        success_criteria="File 'agent_frameworks_comparison.md' exists in workspace with > 100 characters",
                    ),
                ],
            )

            mock_llm = MagicMock()
            mock_structured_planner = MagicMock()
            mock_structured_planner.invoke.return_value = planned_goal
            mock_llm.with_structured_output.return_value = mock_structured_planner

            # Mock LLM report synthesis for step 2
            mock_llm.invoke.return_value = MagicMock(
                content="""# Comparative Architecture Analysis: Open-Source AI Agent Frameworks (2026)

## Executive Summary
This report analyzes and compares three leading open-source agent frameworks: **LangGraph**, **CrewAI**, and **AutoGen**.

## Framework Architectural Comparison

| Framework | Core Paradigm | State Machine / Memory | Multi-Agent Coordination | Best Fit |
|---|---|---|---|---|
| **LangGraph** | Cyclic Directed Graphs (DAGs + Loops) | Centralized TypedDict / Pydantic State | Graph routing & conditional edges | Complex, long-running agent workflows requiring cycles & human-in-the-loop |
| **CrewAI** | Role-Playing Sequential/Hierarchical Teams | Process memory & shared context | Hierarchical delegation & consensus | Business processes, content generation, persona-based teams |
| **AutoGen** | Conversable Multi-Agent Chat | Conversation thread history | Event-driven actor messages | Multi-turn collaborative problem-solving & code sandboxes |

## Key Architectural Trade-offs
1. **Control vs. Autonomy:** LangGraph provides fine-grained deterministic control through explicit state graphs, whereas CrewAI and AutoGen emphasize conversational emergence.
2. **Durability & Streaming:** LangGraph natively supports stream modes (messages, updates, debug) and checkpoint persistence.

## Conclusion & Recommendation
For predictable enterprise pipelines and hackathon applications requiring strict tool validation, **LangGraph** offers the strongest architecture.
"""
            )

            planner = _planner_agent(mock_llm, event_callback=None)
            state = {"user_prompt": user_prompt}
            state.update(planner(state))

            # Verify Step 1: Planner generated research and report steps, not software code files
            self.assertEqual(state["goal_plan"].task_type, "research")
            self.assertEqual(state["goal_plan"].steps[0].tool_name, "web_search")
            self.assertEqual(state["goal_plan"].steps[1].tool_name, "write_file")

            # 2. Architect Phase
            architect = _architect_agent(mock_llm, event_callback=None)
            state.update(architect(state))
            self.assertIn("detailed_ins", state)

            # 3. Execution Phase (Coder/Executor executing step-1 and step-2)
            events = []
            coder = _coder_agent(mock_llm, event_callback=lambda e: events.append(e))

            # Step 1: web_search execution
            fake_search_data = {
                "provider": "duckduckgo",
                "query": state["goal_plan"].steps[0].tool_args["query"],
                "count": 3,
                "results": [
                    {
                        "title": "LangGraph: Cyclic Graph AI Agent Orchestration",
                        "url": "https://langchain.com/langgraph",
                        "snippet": "LangGraph enables stateful, multi-actor applications with LLMs.",
                    },
                    {
                        "title": "CrewAI: Framework for Orchestrating Role-Playing AI Agents",
                        "url": "https://crewai.com",
                        "snippet": "CrewAI empowers autonomous agents to collaborate on complex tasks.",
                    },
                    {
                        "title": "Microsoft AutoGen: Multi-Agent Conversation Framework",
                        "url": "https://microsoft.github.io/autogen",
                        "snippet": "AutoGen enables next-gen LLM applications via multi-agent conversation.",
                    },
                ],
            }

            with patch("agent.tools_registry.GLOBAL_TOOL_REGISTRY.execute") as mock_exec:
                mock_exec.return_value = {
                    "success": True,
                    "data": fake_search_data,
                    "error": None,
                    "started_at": "2026-10-23T10:00:00Z",
                    "completed_at": "2026-10-23T10:00:01Z",
                }

                # Run step 1
                state.update(coder(state))
                self.assertEqual(state["current_step_idx"], 1)
                self.assertEqual(len(state["execution_records"]), 1)
                self.assertEqual(state["execution_records"][0].tool_name, "web_search")
                self.assertEqual(state["execution_records"][0].status, "success")

            # Step 2: write_file execution (synthesize report and write to workspace)
            state.update(coder(state))
            self.assertEqual(state["current_step_idx"], 2)
            self.assertEqual(len(state["execution_records"]), 2)
            self.assertEqual(state["execution_records"][1].tool_name, "write_file")
            self.assertEqual(state["execution_records"][1].status, "success")

            # 4. Final Evaluation & Verification Step (coder called when step_idx >= len(steps))
            final_state = coder(state)
            self.assertEqual(final_state["status"], "DONE")
            self.assertEqual(final_state["objective_status"], "SUCCESS")
            self.assertIsNotNone(final_state["verification"])
            self.assertIn("all 2 planned actions completed", final_state["verification"].evidence_summary)

            # 5. Check real deliverable in the workspace filesystem
            saved_content = read_text_file("agent_frameworks_comparison.md")
            self.assertIn("Comparative Architecture Analysis", saved_content)
            self.assertIn("LangGraph", saved_content)
            self.assertIn("CrewAI", saved_content)
            self.assertIn("AutoGen", saved_content)
            self.assertIn("Framework Architectural Comparison", saved_content)


if __name__ == "__main__":
    unittest.main()

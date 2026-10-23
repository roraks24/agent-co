"""Tests for general-purpose workflow execution, verification, and recovery."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from agent.graph import (
    _coder_agent,
    _evaluate_goal_completion,
    _planner_agent,
)
from agent.state import (
    ActionExecutionRecord,
    ActionStep,
    GoalPlan,
    Plan,
)
from agent.workspace import workspace_context, write_text_file


class GeneralWorkflowPlanningTests(unittest.TestCase):
    def test_general_objective_produces_goal_plan(self) -> None:
        user_prompt = "Research three currently relevant open-source AI agent frameworks and compare them."
        expected_goal_plan = GoalPlan(
            objective=user_prompt,
            task_type="research",
            expected_outcome="Comparative report of 3 AI agent frameworks",
            steps=[
                ActionStep(
                    id="step-1",
                    title="Search Agent Frameworks",
                    tool_name="web_search",
                    tool_args={"query": "open source ai agent frameworks 2026", "max_results": 3},
                    expected_outcome="Key framework articles and architecture info",
                ),
                ActionStep(
                    id="step-2",
                    title="Write Comparison Report",
                    tool_name="write_file",
                    tool_args={"path": "framework_comparison.md"},
                    expected_outcome="Saved Markdown report with comparison table",
                ),
            ],
        )

        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = expected_goal_plan
        mock_llm.with_structured_output.return_value = mock_structured

        planner = _planner_agent(mock_llm, event_callback=None)
        result = planner({"user_prompt": user_prompt})

        self.assertIn("goal_plan", result)
        self.assertIn("plan", result)
        self.assertEqual(result["goal_plan"].task_type, "research")
        self.assertEqual(len(result["goal_plan"].steps), 2)
        self.assertEqual(result["goal_plan"].steps[0].tool_name, "web_search")


class GoalVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.goal_plan = GoalPlan(
            objective="Research AI frameworks and write report",
            task_type="research",
            expected_outcome="Report in workspace",
            steps=[
                ActionStep(id="step-1", title="Search", tool_name="web_search", tool_args={"query": "test"}),
                ActionStep(id="step-2", title="Write", tool_name="write_file", tool_args={"path": "report.md"}),
            ],
        )

    def test_verifier_marks_success_when_all_steps_and_files_verified(self) -> None:
        with workspace_context("test-verif-success"):
            write_text_file("report.md", "# Valid Report\nDetailed comparative findings.")
            records = [
                ActionExecutionRecord(
                    step_id="step-1",
                    tool_name="web_search",
                    tool_args={"query": "test"},
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                    duration_ms=1000,
                    tool_result={"count": 3, "results": [{"title": "Framework"}]},
                    status="success",
                ),
                ActionExecutionRecord(
                    step_id="step-2",
                    tool_name="write_file",
                    tool_args={"path": "report.md"},
                    started_at="2026-01-01T00:00:01Z",
                    completed_at="2026-01-01T00:00:02Z",
                    duration_ms=500,
                    tool_result={"path": "report.md"},
                    status="success",
                ),
            ]
            verif = _evaluate_goal_completion(self.goal_plan, records)
            self.assertEqual(verif.objective_status, "SUCCESS")
            self.assertIn("all 2 planned actions completed", verif.evidence_summary)

    def test_verifier_marks_failed_when_critical_step_or_file_fails(self) -> None:
        with workspace_context("test-verif-fail"):
            # report.md is NOT created
            records = [
                ActionExecutionRecord(
                    step_id="step-1",
                    tool_name="web_search",
                    tool_args={"query": "test"},
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                    duration_ms=1000,
                    tool_result=None,
                    status="failed",
                    error="ConnectionTimeout",
                )
            ]
            verif = _evaluate_goal_completion(self.goal_plan, records)
            self.assertEqual(verif.objective_status, "FAILED")
            self.assertIn("failed", verif.evidence_summary.lower())

    def test_plan_exhaustion_without_deliverable_does_not_claim_success(self) -> None:
        with workspace_context("test-verif-exhausted"):
            # All steps finished execution loop, but step-2 produced empty file
            write_text_file("report.md", "")
            records = [
                ActionExecutionRecord(
                    step_id="step-1",
                    tool_name="web_search",
                    tool_args={"query": "test"},
                    started_at="2026-01-01T00:00:00Z",
                    completed_at="2026-01-01T00:00:01Z",
                    duration_ms=100,
                    tool_result={"count": 0},
                    status="success",
                ),
                ActionExecutionRecord(
                    step_id="step-2",
                    tool_name="write_file",
                    tool_args={"path": "report.md"},
                    started_at="2026-01-01T00:00:01Z",
                    completed_at="2026-01-01T00:00:02Z",
                    duration_ms=100,
                    tool_result={"path": "report.md"},
                    status="success",
                ),
            ]
            verif = _evaluate_goal_completion(self.goal_plan, records)
            # Empty deliverable + 0 search results must NOT be marked SUCCESS
            self.assertNotEqual(verif.objective_status, "SUCCESS")


class CoderExecutionAndRetryTests(unittest.TestCase):
    def test_tool_failure_triggers_bounded_retry(self) -> None:
        with workspace_context("test-coder-retry"):
            mock_llm = MagicMock()
            events = []

            def callback(evt):
                events.append(evt)

            step = ActionStep(
                id="step-1",
                title="Search",
                tool_name="web_search",
                tool_args={"query": "error query"},
                retry_count=0,
            )
            goal_plan = GoalPlan(
                objective="Test retry",
                task_type="research",
                expected_outcome="Out",
                steps=[step],
            )
            state = {
                "goal_plan": goal_plan,
                "current_step_idx": 0,
                "execution_records": [],
            }

            coder = _coder_agent(mock_llm, event_callback=callback)

            with patch("agent.tools_registry.GLOBAL_TOOL_REGISTRY.execute") as mock_exec:
                # First attempt fails
                mock_exec.return_value = {"success": False, "data": None, "error": "RateLimitError"}
                next_state = coder(state)

                # Retry count should increment, step_idx stays at 0 for bounded retry
                self.assertEqual(next_state["goal_plan"].steps[0].retry_count, 1)
                self.assertEqual(next_state["goal_plan"].steps[0].status, "retried")
                self.assertEqual(next_state["current_step_idx"], 0)

                # Second attempt succeeds
                mock_exec.return_value = {"success": True, "data": {"count": 1, "results": []}, "error": None}
                final_step_state = coder(next_state)
                self.assertEqual(final_step_state["goal_plan"].steps[0].status, "completed")
                self.assertEqual(final_step_state["current_step_idx"], 1)


if __name__ == "__main__":
    unittest.main()

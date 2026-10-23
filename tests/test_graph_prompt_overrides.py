from __future__ import annotations

import unittest

from agent.graph import _resolve_node_mutable_prompt
from agent.prompts import default_mutable_for_node


class GraphPromptOverrideTests(unittest.TestCase):
    def test_node_override_precedence(self) -> None:
        state = {
            "mutable_prompt": "legacy mutable prompt",
            "prompt_overrides": {"planner": "planner override"},
        }

        self.assertEqual(_resolve_node_mutable_prompt(state, "planner"), "planner override")
        self.assertEqual(_resolve_node_mutable_prompt(state, "coder"), "legacy mutable prompt")

    def test_default_fallback_when_no_override_or_legacy(self) -> None:
        state = {"prompt_overrides": {}}
        self.assertEqual(
            _resolve_node_mutable_prompt(state, "architect"),
            default_mutable_for_node("architect"),
        )

    def test_planner_override_does_not_leak_to_coder(self) -> None:
        state = {"prompt_overrides": {"planner": "planner-only instruction"}}

        self.assertEqual(
            _resolve_node_mutable_prompt(state, "planner"),
            "planner-only instruction",
        )
        self.assertEqual(
            _resolve_node_mutable_prompt(state, "coder"),
            default_mutable_for_node("coder"),
        )


if __name__ == "__main__":
    unittest.main()

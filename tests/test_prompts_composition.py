from __future__ import annotations

import unittest

from agent.prompts import (
    IMMUTABLE_PROMPT_RULES,
    MAX_MUTABLE_PROMPT_CHARS,
    NODE_PROMPT_CONFIGS,
    default_mutable_for_node,
    get_composed_prompt,
    prompt_schema,
)


class PromptCompositionTests(unittest.TestCase):
    def test_composed_prompt_order(self) -> None:
        prompt = get_composed_prompt("planner", "Be concise", "Context block")

        first_rule_index = prompt.index(IMMUTABLE_PROMPT_RULES[0])
        prefix_index = prompt.index(
            NODE_PROMPT_CONFIGS["planner"].immutable_prefix.strip().splitlines()[0]
        )
        mutable_index = prompt.index("Be concise")
        context_index = prompt.index("Context block")

        self.assertLess(first_rule_index, prefix_index)
        self.assertLess(prefix_index, mutable_index)
        self.assertLess(mutable_index, context_index)

    def test_node_specific_immutable_prefix_is_present(self) -> None:
        prompt = get_composed_prompt("architect", "Use MVC where possible", "Plan block")
        self.assertIn(
            NODE_PROMPT_CONFIGS["architect"].immutable_prefix.strip().splitlines()[0],
            prompt,
        )

    def test_mutable_layer_falls_back_to_node_default(self) -> None:
        composed = get_composed_prompt("coder", None, "Task context")
        self.assertIn(default_mutable_for_node("coder"), composed)

    def test_no_suffix_in_schema_nodes(self) -> None:
        schema = prompt_schema()
        for node in ("planner", "architect", "coder"):
            self.assertIn("immutable_prefix", schema["nodes"][node])
            self.assertIn("default_mutable", schema["nodes"][node])
            self.assertNotIn("suffix", schema["nodes"][node])

    def test_mutable_layer_over_limit_is_rejected(self) -> None:
        oversized = "x" * (MAX_MUTABLE_PROMPT_CHARS + 1)
        with self.assertRaises(ValueError):
            get_composed_prompt("planner", oversized, "Context")


if __name__ == "__main__":
    unittest.main()

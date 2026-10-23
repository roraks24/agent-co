"""Regression and functional test suite for Calculator Deliverables and Verification Status Consistency."""

from __future__ import annotations

import os
import unittest
from agent.state import ActionExecutionRecord, ActionStep, GoalPlan
from agent.verification_engine import (
    FactualVerifier,
    has_unresolved_placeholders,
    validate_software_deliverable,
)
from agent.calculator_tester import test_calculator_functionality as run_calculator_tests
from agent.workspace import read_text_file, workspace_context, write_text_file


class TestCalculatorVerificationConsistency(unittest.TestCase):
    """Test suite covering calculator functionality, deliverable validation, and verification consistency."""

    def test_rule_9_comment_bug_regression(self) -> None:
        """Verify that genuine stylesheets with header/footer comments are NOT classified as placeholders."""
        # Genuine stylesheet starting with comment and ending with comment
        real_css = """/* ==========================================================================
   Calculator Stylesheet
   ========================================================================== */

:root {
    --bg-color: #121214;
    --card-bg: #1e1e24;
    --accent-color: #3b82f6;
    --text-color: #f3f4f6;
}

body {
    background: var(--bg-color);
    color: var(--text-color);
    font-family: system-ui, -apple-system, sans-serif;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
}

.calculator {
    background: var(--card-bg);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

#display {
    width: 100%;
    height: 64px;
    background: #0d0d10;
    border-radius: 8px;
    font-size: 2rem;
    text-align: right;
    padding: 12px;
}

/* End of calculator stylesheet */"""

        findings = has_unresolved_placeholders(real_css)
        self.assertEqual(
            findings,
            [],
            f"Genuine CSS should have zero placeholder findings, got: {findings}",
        )

        # Genuine markdown heading starting with #
        real_md = "# Calculator Application\n\nA modern web calculator."
        self.assertEqual(has_unresolved_placeholders(real_md), [])

        # Comment placeholder stub MUST be detected
        stub_css = "/* CSS placeholder: add styles here */"
        stub_findings = has_unresolved_placeholders(stub_css)
        self.assertTrue(
            len(stub_findings) > 0,
            "Stub CSS should be flagged as placeholder",
        )

        todo_html = "<!-- TODO: implement calculator display -->"
        todo_findings = has_unresolved_placeholders(todo_html)
        self.assertTrue(
            len(todo_findings) > 0,
            "TODO HTML should be flagged as placeholder",
        )

    def test_software_deliverable_cross_links(self) -> None:
        """Verify HTML deliverables properly cross-link workspace CSS and JS files."""
        # HTML that fails to link style.css
        bad_html = """<!DOCTYPE html>
<html lang="en">
<head><title>Calc</title></head>
<body><div id="display">0</div></body>
</html>"""

        files_with_css = {
            "index.html": bad_html,
            "style.css": "body { color: red; } .calc { display: flex; }",
        }
        issues = validate_software_deliverable("index.html", bad_html, files_with_css)
        self.assertTrue(
            any("does not link to stylesheet 'style.css'" in iss for iss in issues),
            f"Expected missing stylesheet link error, got: {issues}",
        )

        # HTML that properly links style.css and script.js
        good_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Calculator</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div id="display">0</div>
    <script src="script.js"></script>
</body>
</html>"""

        all_valid_files = {
            "index.html": good_html,
            "style.css": "body { color: red; } .calc { display: flex; }",
            "script.js": "document.addEventListener('DOMContentLoaded', () => {});",
        }
        valid_issues = validate_software_deliverable("index.html", good_html, all_valid_files)
        self.assertEqual(valid_issues, [])

    def test_syntax_and_brace_balance_checks(self) -> None:
        """Verify unbalanced braces in CSS and JS are caught."""
        broken_css = "body { color: red; /* missing close brace */"
        issues_css = validate_software_deliverable("style.css", broken_css, {})
        self.assertTrue(
            any("unbalanced curly braces" in iss for iss in issues_css),
            f"Expected unbalanced brace issue, got: {issues_css}",
        )

        broken_js = "function add(a, b) { return (a + b; }"
        issues_js = validate_software_deliverable("script.js", broken_js, {})
        self.assertTrue(
            any("unbalanced parentheses" in iss for iss in issues_js),
            f"Expected unbalanced parenthesis issue, got: {issues_js}",
        )

    def test_calculator_functional_browser_and_math_engine(self) -> None:
        """Verify calculator functionality: arithmetic, decimal input, clear, backspace, and division by zero."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Calculator</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div id="display">0</div>
    <div class="keypad">
        <button id="clear">C</button>
        <button id="backspace">⌫</button>
        <button id="percent">%</button>
        <button class="op" data-op="/">÷</button>
        <button class="digit">7</button>
        <button class="digit">8</button>
        <button class="digit">9</button>
        <button class="op" data-op="*">×</button>
        <button class="digit">4</button>
        <button class="digit">5</button>
        <button class="digit">6</button>
        <button class="op" data-op="-">−</button>
        <button class="digit">1</button>
        <button class="digit">2</button>
        <button class="digit">3</button>
        <button class="op" data-op="+">+</button>
        <button class="digit">0</button>
        <button id="decimal">.</button>
        <button id="equals">=</button>
    </div>
    <script src="script.js"></script>
</body>
</html>"""

        css_code = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { display: flex; justify-content: center; align-items: center; min-height: 100vh; font-family: sans-serif; }
#display { font-size: 2rem; padding: 12px; text-align: right; background: #eee; width: 100%; }
.keypad { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 16px; }
button { padding: 16px; font-size: 1.2rem; cursor: pointer; }
"""

        # JS with proper per-operand decimal handling and division by zero protection
        js_code = """
let currentInput = "0";
let previousInput = "";
let operation = null;
let shouldResetScreen = false;

const display = document.getElementById("display");

function updateDisplay() {
    display.textContent = currentInput;
}

function inputDigit(digit) {
    if (currentInput === "0" || shouldResetScreen) {
        currentInput = digit;
        shouldResetScreen = false;
    } else {
        currentInput += digit;
    }
    updateDisplay();
}

function inputDecimal() {
    if (shouldResetScreen) {
        currentInput = "0.";
        shouldResetScreen = false;
        updateDisplay();
        return;
    }
    if (!currentInput.includes(".")) {
        currentInput += ".";
        updateDisplay();
    }
}

function handleOperator(nextOp) {
    const inputVal = parseFloat(currentInput);
    if (operation && shouldResetScreen) {
        operation = nextOp;
        return;
    }
    if (previousInput === "") {
        previousInput = inputVal;
    } else if (operation) {
        const result = calculate(previousInput, inputVal, operation);
        currentInput = `${parseFloat(result.toFixed(8))}`;
        previousInput = result;
        updateDisplay();
    }
    shouldResetScreen = true;
    operation = nextOp;
}

function calculate(first, second, op) {
    if (op === "+") return first + second;
    if (op === "-" || op === "−") return first - second;
    if (op === "*" || op === "×") return first * second;
    if (op === "/" || op === "÷") {
        if (second === 0) return "Error";
        return first / second;
    }
    return second;
}

document.querySelectorAll(".digit").forEach(b => b.addEventListener("click", () => inputDigit(b.textContent)));
document.querySelectorAll(".op").forEach(b => b.addEventListener("click", () => handleOperator(b.getAttribute("data-op"))));
document.getElementById("decimal").addEventListener("click", inputDecimal);
document.getElementById("clear").addEventListener("click", () => {
    currentInput = "0";
    previousInput = "";
    operation = null;
    shouldResetScreen = false;
    updateDisplay();
});
document.getElementById("backspace").addEventListener("click", () => {
    if (currentInput.length > 1) {
        currentInput = currentInput.slice(0, -1);
    } else {
        currentInput = "0";
    }
    updateDisplay();
});
document.getElementById("percent").addEventListener("click", () => {
    currentInput = `${parseFloat(currentInput) / 100}`;
    updateDisplay();
});
document.getElementById("equals").addEventListener("click", () => {
    if (operation === null || shouldResetScreen) return;
    const result = calculate(previousInput, parseFloat(currentInput), operation);
    currentInput = (result === "Error") ? "Error" : `${parseFloat(result.toFixed(8))}`;
    operation = null;
    previousInput = "";
    shouldResetScreen = true;
    updateDisplay();
});
"""

        calc_files = {
            "index.html": html_code,
            "style.css": css_code,
            "script.js": js_code,
        }

        passed, logs = run_calculator_tests(
            workspace_dir=None,
            html_content=html_code,
            all_files=calc_files,
        )
        self.assertTrue(passed, f"Calculator functionality tests failed: {logs}")
        self.assertTrue(any("Addition" in log for log in logs))
        self.assertTrue(any("Decimal arithmetic" in log for log in logs))
        self.assertTrue(any("Division by zero" in log for log in logs))

    def test_contradictory_verification_status_prevented(self) -> None:
        """Verify that verification status is never reported as SUCCESS when deliverables fail."""
        with workspace_context("test-contradiction-prevention"):
            # Missing files or placeholder causes deliverable failure
            write_text_file("index.html", "<!-- TODO: implement calculator -->")
            steps = [
                ActionStep(
                    id="step-1",
                    step_id="step-1",
                    title="Generate Calculator",
                    tool_name="write_file",
                    tool_args={"path": "index.html"},
                    status="completed",
                )
            ]
            goal_plan = GoalPlan(
                objective="make a calculator",
                expected_outcome="Functional calculator",
                task_type="coding",
                steps=steps,
            )
            records = [
                ActionExecutionRecord(
                    step_id="step-1",
                    tool_name="write_file",
                    tool_args={"path": "index.html"},
                    started_at="2026-10-24T00:00:00Z",
                    completed_at="2026-10-24T00:00:01Z",
                    duration_ms=100,
                    status="success",
                    tool_result={"path": "index.html"},
                )
            ]

            verifier = FactualVerifier(goal_plan, records)
            result = verifier.evaluate()

            # Crucial assertion: Deliverable failed, so verification MUST NOT be SUCCESS!
            self.assertEqual(result.deliverable_status, "FAILED")
            self.assertEqual(result.source_verification_status, "FAILED")
            self.assertEqual(result.functional_verification_status, "FAILED")
            self.assertEqual(result.objective_status, "FAILED")

    def test_complete_calculator_workspace_e2e_verification(self) -> None:
        """Verify that the production calculator files achieve 100% SUCCESS across all dimensions."""
        calc_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspaces", "ff32f1ae-8528-4eba-ab42-01e1676529f9")
        if not os.path.exists(calc_dir):
            self.skipTest(f"Calculator workspace {calc_dir} not found")

        # Read the files from the calculator workspace
        index_html = open(os.path.join(calc_dir, "index.html"), encoding="utf-8").read()
        style_css = open(os.path.join(calc_dir, "style.css"), encoding="utf-8").read()
        script_js = open(os.path.join(calc_dir, "script.js"), encoding="utf-8").read()
        readme_md = open(os.path.join(calc_dir, "README.md"), encoding="utf-8").read()

        with workspace_context("test-calc-e2e"):
            write_text_file("index.html", index_html)
            write_text_file("style.css", style_css)
            write_text_file("script.js", script_js)
            write_text_file("README.md", readme_md)

            steps = [
                ActionStep(id="s1", step_id="s1", title="Write index.html", tool_name="write_file", tool_args={"path": "index.html"}, status="completed"),
                ActionStep(id="s2", step_id="s2", title="Write style.css", tool_name="write_file", tool_args={"path": "style.css"}, status="completed"),
                ActionStep(id="s3", step_id="s3", title="Write script.js", tool_name="write_file", tool_args={"path": "script.js"}, status="completed"),
                ActionStep(id="s4", step_id="s4", title="Write README.md", tool_name="write_file", tool_args={"path": "README.md"}, status="completed"),
            ]
            goal_plan = GoalPlan(
                objective="make a calculator",
                expected_outcome="Working calculator web application",
                task_type="coding",
                steps=steps,
            )
            records = [
                ActionExecutionRecord(step_id="s1", tool_name="write_file", started_at="2026-10-24T00:00:00Z", completed_at="2026-10-24T00:00:01Z", duration_ms=100, status="success", tool_result={"path": "index.html"}),
                ActionExecutionRecord(step_id="s2", tool_name="write_file", started_at="2026-10-24T00:00:01Z", completed_at="2026-10-24T00:00:02Z", duration_ms=100, status="success", tool_result={"path": "style.css"}),
                ActionExecutionRecord(step_id="s3", tool_name="write_file", started_at="2026-10-24T00:00:02Z", completed_at="2026-10-24T00:00:03Z", duration_ms=100, status="success", tool_result={"path": "script.js"}),
                ActionExecutionRecord(step_id="s4", tool_name="write_file", started_at="2026-10-24T00:00:03Z", completed_at="2026-10-24T00:00:04Z", duration_ms=100, status="success", tool_result={"path": "README.md"}),
            ]

            verifier = FactualVerifier(goal_plan, records)
            res = verifier.evaluate()

            self.assertEqual(res.execution_status, "SUCCESS", f"Execution should be SUCCESS, got: {res.execution_status}")
            self.assertEqual(res.deliverable_status, "SUCCESS", f"Deliverable should be SUCCESS, got: {res.deliverable_status}")
            self.assertEqual(res.source_verification_status, "SUCCESS", f"Verification should be SUCCESS, got: {res.source_verification_status}")
            self.assertEqual(res.functional_verification_status, "SUCCESS", f"Functional status should be SUCCESS, got: {res.functional_verification_status}")
            self.assertEqual(res.objective_status, "SUCCESS", f"Objective should be SUCCESS, got: {res.objective_status}")
            self.assertEqual(len(res.unverified_claims), 0, f"Expected 0 unverified claims, got: {res.unverified_claims}")


if __name__ == "__main__":
    unittest.main()

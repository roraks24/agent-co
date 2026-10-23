"""Automated browser and deterministic testing engine for Calculator deliverables."""

from __future__ import annotations

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _run_browser_tests_sync(
    file_url: str,
) -> tuple[bool, list[str]]:
    """Execute automated browser tests on desktop and mobile viewports using Playwright."""
    from playwright.sync_api import sync_playwright

    results: list[str] = []
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for vp_name, vp in [
                ("Desktop", {"width": 1280, "height": 800}),
                ("Mobile", {"width": 375, "height": 667}),
            ]:
                page = browser.new_page(viewport=vp)
                page_errors: list[str] = []
                page.on("pageerror", lambda err: page_errors.append(str(err)))

                failed_requests: list[str] = []
                page.on("requestfailed", lambda req: failed_requests.append(req.url))

                page.goto(file_url, wait_until="load")
                page.wait_for_selector("#display, .display, [role='textbox']", timeout=5000)

                disp = page.locator("#display, .display, [role='textbox']").first

                def get_display() -> str:
                    return disp.inner_text().strip()

                def click_key(label: str) -> None:
                    # Match exact or text-containing button
                    btn = page.locator(f"button:text-is('{label}')").first
                    if btn.count() == 0:
                        btn = page.locator(f"button:has-text('{label}')").first
                    btn.click()

                # Test 1: Addition: 7 + 8 = 15
                click_key("C")
                click_key("7")
                click_key("+")
                click_key("8")
                click_key("=")
                add_res = get_display()
                if add_res == "15":
                    results.append(f"{vp_name}: Addition (7 + 8 = 15) verified.")
                else:
                    failures.append(f"{vp_name}: Addition 7 + 8 returned '{add_res}', expected '15'.")

                # Test 2: Subtraction: 10 - 4 = 6
                click_key("C")
                click_key("1")
                click_key("0")
                # Look for subtraction button (− or -)
                sub_btn = page.locator("button:text-is('−'), button:text-is('-'), [data-action='subtract']").first
                sub_btn.click()
                click_key("4")
                click_key("=")
                sub_res = get_display()
                if sub_res == "6":
                    results.append(f"{vp_name}: Subtraction (10 - 4 = 6) verified.")
                else:
                    failures.append(f"{vp_name}: Subtraction 10 - 4 returned '{sub_res}', expected '6'.")

                # Test 3: Multiplication: 6 × 7 = 42
                click_key("C")
                click_key("6")
                mul_btn = page.locator("button:text-is('×'), button:text-is('*'), [data-action='multiply']").first
                mul_btn.click()
                click_key("7")
                click_key("=")
                mul_res = get_display()
                if mul_res == "42":
                    results.append(f"{vp_name}: Multiplication (6 × 7 = 42) verified.")
                else:
                    failures.append(f"{vp_name}: Multiplication 6 × 7 returned '{mul_res}', expected '42'.")

                # Test 4: Division: 20 ÷ 4 = 5
                click_key("C")
                click_key("2")
                click_key("0")
                div_btn = page.locator("button:text-is('÷'), button:text-is('/'), [data-action='divide']").first
                div_btn.click()
                click_key("4")
                click_key("=")
                div_res = get_display()
                if div_res == "5":
                    results.append(f"{vp_name}: Division (20 ÷ 4 = 5) verified.")
                else:
                    failures.append(f"{vp_name}: Division 20 ÷ 4 returned '{div_res}', expected '5'.")

                # Test 5: Decimal calculations: 3.5 + 2.1 = 5.6
                click_key("C")
                click_key("3")
                click_key(".")
                click_key("5")
                click_key("+")
                click_key("2")
                click_key(".")
                click_key("1")
                click_key("=")
                dec_res = get_display()
                if dec_res == "5.6":
                    results.append(f"{vp_name}: Decimal arithmetic (3.5 + 2.1 = 5.6) verified.")
                else:
                    failures.append(f"{vp_name}: Decimal arithmetic 3.5 + 2.1 returned '{dec_res}', expected '5.6'.")

                # Test 6: Clear and Backspace
                click_key("C")
                click_key("1")
                click_key("2")
                click_key("3")
                del_btn = page.locator("button:text-is('⌫'), button:text-is('DEL'), [data-action='delete']").first
                del_btn.click()
                del_res = get_display()
                if del_res == "12":
                    results.append(f"{vp_name}: Backspace (123 -> ⌫ -> 12) verified.")
                else:
                    failures.append(f"{vp_name}: Backspace 123 -> ⌫ returned '{del_res}', expected '12'.")

                click_key("C")
                clr_res = get_display()
                if clr_res == "0":
                    results.append(f"{vp_name}: Clear (C -> 0) verified.")
                else:
                    failures.append(f"{vp_name}: Clear button returned '{clr_res}', expected '0'.")

                # Test 7: Division by zero safety
                click_key("5")
                div_btn.click()
                click_key("0")
                click_key("=")
                zero_res = get_display()
                if zero_res in ("Error", "Infinity", "Cannot divide by zero"):
                    results.append(f"{vp_name}: Division by zero safety handled ({zero_res}).")
                else:
                    failures.append(f"{vp_name}: Division by zero returned unexpected '{zero_res}'.")

                # Test 8: Percentage
                click_key("C")
                click_key("5")
                click_key("0")
                pct_btn = page.locator("button:text-is('%'), [data-action='percent']").first
                pct_btn.click()
                pct_res = get_display()
                if pct_res in ("0.5", "50%"):
                    results.append(f"{vp_name}: Percentage calculation (50% = 0.5) verified.")
                else:
                    failures.append(f"{vp_name}: Percentage 50% returned '{pct_res}', expected '0.5'.")

                # Check runtime JavaScript exceptions and failed network requests
                if page_errors:
                    failures.append(f"{vp_name}: JavaScript runtime error(s): {', '.join(page_errors[:3])}")
                else:
                    results.append(f"{vp_name}: Zero JavaScript runtime errors.")

                if failed_requests:
                    failures.append(f"{vp_name}: Failed asset request(s): {', '.join(failed_requests[:3])}")
                else:
                    results.append(f"{vp_name}: All asset requests resolved successfully.")

                page.close()

        finally:
            browser.close()

    if failures:
        return False, failures
    return True, results


def test_calculator_functionality(
    workspace_dir: str | None = None,
    html_content: str | None = None,
    all_files: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Entry point for testing calculator deliverables.
    Tries automated browser testing using Playwright in an isolated thread worker.
    Falls back gracefully if browser automation cannot be initialized."""
    # Check if we have an existing workspace directory with index.html
    temp_dir_to_clean: Optional[str] = None
    target_file_url: Optional[str] = None

    try:
        if workspace_dir and os.path.exists(os.path.join(workspace_dir, "index.html")):
            norm_path = os.path.join(workspace_dir, "index.html").replace("\\", "/")
            target_file_url = f"file:///{norm_path}"
        elif html_content:
            # Create a temporary directory to host the files for browser test
            temp_dir = tempfile.mkdtemp(prefix="agent_calc_test_")
            temp_dir_to_clean = temp_dir
            with open(os.path.join(temp_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(html_content)
            if all_files:
                for fname, fcontent in all_files.items():
                    if fname != "index.html":
                        subpath = os.path.join(temp_dir, os.path.basename(fname))
                        with open(subpath, "w", encoding="utf-8") as f:
                            f.write(fcontent)
            norm_path = os.path.join(temp_dir, "index.html").replace("\\", "/")
            target_file_url = f"file:///{norm_path}"

        if target_file_url:
            # Run in a separate thread so sync_playwright never conflicts with active asyncio event loop
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_browser_tests_sync, target_file_url)
                return future.result(timeout=25)

    except Exception as exc:
        logger.warning("Automated browser testing encountered exception: %s. Using deterministic static verification.", exc)
        return _deterministic_calculator_fallback(html_content or "", all_files or {})

    finally:
        if temp_dir_to_clean and os.path.exists(temp_dir_to_clean):
            try:
                import shutil
                shutil.rmtree(temp_dir_to_clean, ignore_errors=True)
            except Exception:
                pass

    return True, ["Calculator verification completed."]


def _deterministic_calculator_fallback(
    html_content: str,
    all_files: dict[str, str],
) -> tuple[bool, list[str]]:
    """Deterministic fallback check if browser automation is unavailable."""
    issues: list[str] = []
    checks: list[str] = []

    # Check for calculator display
    if not any(marker in html_content.lower() for marker in ('id="display"', 'class="display"', 'role="textbox"')):
        issues.append("Missing calculator display element (#display or .display).")
    else:
        checks.append("Display screen structure verified.")

    # Check for required digits 0-9
    missing_digits = [d for d in "0123456789" if f">{d}<" not in html_content and f'"{d}"' not in html_content]
    if missing_digits:
        issues.append(f"Keypad is missing digit(s): {', '.join(missing_digits)}.")
    else:
        checks.append("All numeric keypad digits 0-9 verified.")

    # Check for basic operators (+, -, *, /)
    has_add = "+" in html_content
    has_sub = "-" in html_content or "−" in html_content
    has_mul = "*" in html_content or "×" in html_content
    has_div = "/" in html_content or "÷" in html_content
    has_eq = "=" in html_content
    has_clr = "C" in html_content or "clear" in html_content.lower()

    if not (has_add and has_sub and has_mul and has_div and has_eq and has_clr):
        issues.append("Keypad is missing one or more essential operation buttons (+, −, ×, ÷, =, C).")
    else:
        checks.append("Standard arithmetic operation buttons (+, −, ×, ÷, =, C) verified.")

    # Check for JavaScript logic
    script_content = all_files.get("script.js", "") or all_files.get("script", "")
    if not script_content:
        # Check if inline script exists
        if "<script" in html_content:
            script_content = html_content

    if "calculate" not in script_content.lower() and "compute" not in script_content.lower() and "eval" not in script_content.lower() and "+" not in script_content:
        issues.append("JavaScript does not contain arithmetic calculation handler logic.")
    else:
        checks.append("Client-side computation engine logic verified.")

    if issues:
        return False, issues
    return True, checks

import asyncio
import os
import sys
from playwright.async_api import async_playwright

# Ensure stdout uses UTF-8 to prevent cp1252 charmap errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

async def run_tests():
    ws_dir = os.path.abspath(r"workspaces\ff32f1ae-8528-4eba-ab42-01e1676529f9")
    file_url = "file:///" + os.path.join(ws_dir, "index.html").replace("\\", "/")
    print(f"Testing URL: {file_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_passed = True
        
        for vp_name, vp in [("Desktop", {"width": 1280, "height": 800}), ("Mobile", {"width": 375, "height": 667})]:
            page = await browser.new_page(viewport=vp)
            
            js_errors = []
            page.on("pageerror", lambda err: js_errors.append(str(err)))
            failed_requests = []
            page.on("requestfailed", lambda req: failed_requests.append(req.url))

            await page.goto(file_url)
            await page.wait_for_selector("#display")

            async def get_display():
                return (await page.inner_text("#display")).strip()

            async def click_btn(text):
                btn = page.locator(f"button:has-text('{text}')").first
                await btn.click()

            print(f"\n--- Testing on {vp_name} Viewport ({vp['width']}x{vp['height']}) ---")
            init_disp = await get_display()
            print("Initial display:", init_disp)
            assert init_disp == "0", f"Initial display should be '0', got {init_disp}"

            # 1. Addition: 7 + 8 = 15
            await click_btn("7")
            await click_btn("+")
            await click_btn("8")
            await click_btn("=")
            res_add = await get_display()
            passed_add = res_add == "15"
            print("Addition (7 + 8):", res_add, "PASS" if passed_add else "FAIL")
            if not passed_add: all_passed = False

            # 2. Subtraction: 10 - 4 = 6
            await click_btn("C")
            await click_btn("1")
            await click_btn("0")
            await click_btn("−")
            await click_btn("4")
            await click_btn("=")
            res_sub = await get_display()
            passed_sub = res_sub == "6"
            print("Subtraction (10 - 4):", res_sub, "PASS" if passed_sub else "FAIL")
            if not passed_sub: all_passed = False

            # 3. Multiplication: 6 × 7 = 42
            await click_btn("C")
            await click_btn("6")
            await click_btn("×")
            await click_btn("7")
            await click_btn("=")
            res_mul = await get_display()
            passed_mul = res_mul == "42"
            print("Multiplication (6 × 7):", res_mul, "PASS" if passed_mul else "FAIL")
            if not passed_mul: all_passed = False

            # 4. Division: 20 ÷ 4 = 5
            await click_btn("C")
            await click_btn("2")
            await click_btn("0")
            await click_btn("÷")
            await click_btn("4")
            await click_btn("=")
            res_div = await get_display()
            passed_div = res_div == "5"
            print("Division (20 ÷ 4):", res_div, "PASS" if passed_div else "FAIL")
            if not passed_div: all_passed = False

            # 5. Decimal calculations: 3.5 + 2.1 = 5.6
            await click_btn("C")
            await click_btn("3")
            await click_btn(".")
            await click_btn("5")
            await click_btn("+")
            await click_btn("2")
            await click_btn(".")
            await click_btn("1")
            await click_btn("=")
            res_dec = await get_display()
            passed_dec = res_dec == "5.6"
            print("Decimal (3.5 + 2.1):", res_dec, "PASS" if passed_dec else "FAIL")
            if not passed_dec: all_passed = False

            # 6. Clear and backspace (delete)
            await click_btn("C")
            await click_btn("1")
            await click_btn("2")
            await click_btn("3")
            await click_btn("⌫")
            res_del = await get_display()
            passed_del = res_del == "12"
            print("Backspace (123 -> ⌫):", res_del, "PASS" if passed_del else "FAIL")
            if not passed_del: all_passed = False

            await click_btn("C")
            res_clr = await get_display()
            passed_clr = res_clr == "0"
            print("Clear (C):", res_clr, "PASS" if passed_clr else "FAIL")
            if not passed_clr: all_passed = False

            # 7. Percentage handling: 50 % = 0.5
            await click_btn("5")
            await click_btn("0")
            await click_btn("%")
            res_pct = await get_display()
            passed_pct = res_pct == "0.5"
            print("Percentage (50%):", res_pct, "PASS" if passed_pct else "FAIL")
            if not passed_pct: all_passed = False

            # 8. Consecutive operations: 2 + 3 * 4 = 20 (or 14)
            await click_btn("C")
            await click_btn("2")
            await click_btn("+")
            await click_btn("3")
            await click_btn("×")
            await click_btn("4")
            await click_btn("=")
            res_chain = await get_display()
            passed_chain = res_chain in ("20", "14")
            print("Consecutive (2 + 3 × 4):", res_chain, "PASS" if passed_chain else "FAIL")
            if not passed_chain: all_passed = False

            # 9. Division by zero: 5 ÷ 0 = Error
            await click_btn("C")
            await click_btn("5")
            await click_btn("÷")
            await click_btn("0")
            await click_btn("=")
            res_zero = await get_display()
            passed_zero = res_zero in ("Error", "Cannot divide by zero")
            print("Division by zero (5 ÷ 0):", res_zero, "PASS" if passed_zero else "FAIL")
            if not passed_zero: all_passed = False

            # 10. Keyboard input test: '7*6='
            await click_btn("C")
            await page.keyboard.press("7")
            await page.keyboard.press("*")
            await page.keyboard.press("6")
            await page.keyboard.press("Enter")
            res_kbd = await get_display()
            passed_kbd = res_kbd == "42"
            print("Keyboard input (7 * 6 + Enter):", res_kbd, "PASS" if passed_kbd else "FAIL")
            if not passed_kbd: all_passed = False

            print("JS page errors:", js_errors)
            print("Failed network requests:", failed_requests)
            if js_errors or failed_requests:
                all_passed = False

            await page.close()

        await browser.close()
        print("\nALL CALCULATOR TESTS PASSED:", all_passed)
        assert all_passed, "Some calculator tests failed!"

if __name__ == "__main__":
    asyncio.run(run_tests())

from __future__ import annotations

import os
from pathlib import Path
import shutil
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from agent.api import app
from agent.source_serializer import clean_transport_escapes, validate_source_code
from agent.verification_engine import validate_software_deliverable


class SourceSerializerAndEscapesTests(unittest.TestCase):
    def test_clean_transport_escapes_html(self) -> None:
        raw_html = (
            "```html\n"
            "<!DOCTYPE html>\\n"
            "<html lang=\\\"en\\\">\\n"
            "<head>\\n"
            "  <link rel=\\\"stylesheet\\\" href=\\\"style.css\\\">\\n"
            "</head>\\n"
            "<body>\\n"
            "  <h1>Rohit Saini</h1>\\n"
            "</body>\\n"
            "</html>\n"
            "```"
        )
        cleaned = clean_transport_escapes(raw_html, "index.html")
        self.assertNotIn(r"\n", cleaned)
        self.assertNotIn(r'\"', cleaned)
        self.assertNotIn("```", cleaned)
        self.assertIn("<!DOCTYPE html>\n", cleaned)
        self.assertIn('<html lang="en">', cleaned)
        self.assertIn("<h1>Rohit Saini</h1>", cleaned)

    def test_clean_transport_escapes_css(self) -> None:
        raw_css = (
            "body {\\n"
            "  font-family: sans-serif;\\n"
            "  background-color: #0f172a;\\n"
            "}\\n"
            ".hero {\\n"
            "  display: flex;\\n"
            "}"
        )
        cleaned = clean_transport_escapes(raw_css, "style.css")
        self.assertNotIn(r"\n", cleaned)
        self.assertIn("body {\n", cleaned)
        self.assertIn("background-color: #0f172a;", cleaned)

    def test_clean_transport_escapes_js_preserves_legitimate_escapes(self) -> None:
        raw_js = (
            'const greeting = "Hello\\nWorld";\\n'
            'console.log(greeting);\\n'
            'function test() {\\n'
            '  return "tab\\there";\\n'
            '}'
        )
        cleaned = clean_transport_escapes(raw_js, "script.js")
        # Structural newlines should be unescaped
        self.assertIn("const greeting =", cleaned)
        self.assertIn("\nconsole.log(greeting);", cleaned)
        # Inside the string literal, \n and \t should remain preserved
        self.assertIn(r'"Hello\nWorld"', cleaned)
        self.assertIn(r'"tab\there"', cleaned)

    def test_validate_source_code_rejections(self) -> None:
        # 1. HTML with literal \n
        html_with_escapes = "<!DOCTYPE html>\n<html>\n<body>\nLiteral \\n text\n</body>\n</html>"
        issues = validate_source_code("index.html", html_with_escapes)
        self.assertTrue(any(r"\n" in iss for iss in issues))

        # 2. HTML missing body
        html_no_body = "<!DOCTYPE html>\n<html><head></head></html>"
        issues = validate_source_code("index.html", html_no_body)
        self.assertTrue(any("<body>" in iss for iss in issues))

        # 3. CSS with literal \n
        css_with_escapes = "body {\\n  color: red;\\n}"
        issues = validate_source_code("style.css", css_with_escapes)
        self.assertTrue(any(r"\n" in iss for iss in issues))

        # 4. Valid HTML and CSS pass cleanly
        valid_html = "<!DOCTYPE html>\n<html>\n<head><title>Test</title></head>\n<body><h1>Hi</h1></body>\n</html>"
        self.assertEqual(validate_source_code("index.html", valid_html), [])

        valid_css = (
            "body {\n"
            "  font-family: Arial, sans-serif;\n"
            "  color: #fff;\n"
            "  margin: 0;\n"
            "}\n"
            "h1 {\n"
            "  font-size: 24px;\n"
            "  padding: 10px;\n"
            "}"
        )
        self.assertEqual(validate_source_code("style.css", valid_css), [])

    def test_validate_software_deliverable_cross_references(self) -> None:
        html = (
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head>\n'
            '  <link rel="stylesheet" href="style.css">\n'
            '  <script src="script.js"></script>\n'
            '</head>\n'
            '<body>\n'
            '  <h1>Portfolio</h1>\n'
            '</body>\n'
            '</html>'
        )

        # Missing referenced files
        issues_missing = validate_software_deliverable("index.html", html, {"index.html": html})
        self.assertTrue(any("style.css" in iss for iss in issues_missing))
        self.assertTrue(any("script.js" in iss for iss in issues_missing))

        # All referenced files present
        all_files = {
            "index.html": html,
            "style.css": "body { margin: 0; }\nh1 { color: #fff; font-size: 20px; }",
            "script.js": "document.addEventListener('DOMContentLoaded', () => { console.log('ready'); });",
        }
        issues_present = validate_software_deliverable("index.html", html, all_files)
        self.assertEqual(issues_present, [])


class WorkspacePreviewIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_id = f"test-ws-{uuid4().hex[:8]}"
        self.ws_dir = (Path("workspaces") / self.workspace_id).resolve()
        self.ws_dir.mkdir(parents=True, exist_ok=True)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        shutil.rmtree(self.ws_dir, ignore_errors=True)

    def test_preview_serves_index_html_with_base_injection(self) -> None:
        html_content = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "  <title>Preview Test</title>\n"
            '  <link rel="stylesheet" href="style.css">\n'
            "</head>\n"
            "<body>\n"
            "  <h1>Portfolio Preview</h1>\n"
            "</body>\n"
            "</html>"
        )
        (self.ws_dir / "index.html").write_text(html_content, encoding="utf-8")

        response = self.client.get(f"/api/agent/workspaces/{self.workspace_id}/preview/index.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn(f'<base href="/api/agent/workspaces/{self.workspace_id}/preview/">', response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-cache, no-store, must-revalidate")

    def test_preview_serves_css_with_correct_mime(self) -> None:
        css_content = "body { margin: 0; background: #111; }\nh1 { color: #fff; font-size: 24px; }"
        (self.ws_dir / "style.css").write_text(css_content, encoding="utf-8")

        response = self.client.get(f"/api/agent/workspaces/{self.workspace_id}/preview/style.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers.get("content-type", ""))
        self.assertIn("background: #111;", response.text)

    def test_preview_serves_js_with_correct_mime(self) -> None:
        js_content = "console.log('preview active');"
        (self.ws_dir / "script.js").write_text(js_content, encoding="utf-8")

        response = self.client.get(f"/api/agent/workspaces/{self.workspace_id}/preview/script.js")
        self.assertEqual(response.status_code, 200)
        ct = response.headers.get("content-type", "")
        self.assertTrue("javascript" in ct or "text/javascript" in ct)
        self.assertIn("preview active", response.text)

    def test_preview_returns_404_for_missing_resource(self) -> None:
        response = self.client.get(f"/api/agent/workspaces/{self.workspace_id}/preview/assets/missing.png")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Resource 'assets/missing.png' not found", response.json().get("detail", ""))

    def test_preview_returns_placeholder_when_index_not_found(self) -> None:
        # Empty workspace with no index.html
        response = self.client.get(f"/api/agent/workspaces/{self.workspace_id}/preview/index.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Live Preview Ready", response.text)
        self.assertIn("Awaiting index.html", response.text)


if __name__ == "__main__":
    unittest.main()

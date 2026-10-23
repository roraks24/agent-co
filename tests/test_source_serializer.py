"""Tests for source code serialization, escape cleanup, and validation."""

import pytest
from agent.source_serializer import clean_transport_escapes, validate_source_code


def test_html_transport_escapes_cleaned():
    raw_escaped = '<!DOCTYPE html>\\n<html lang=\\"en\\">\\n<head>\\n    <title>Portfolio</title>\\n    <link rel="stylesheet" href="style.css">\\n</head>\\n<body>\\n    <h1>Rohit Saini</h1>\\n</body>\\n</html>'
    cleaned = clean_transport_escapes(raw_escaped, "index.html")

    assert "\\n" not in cleaned
    assert '\\"' not in cleaned
    assert '\n' in cleaned
    assert '<html lang="en">' in cleaned
    assert "<!DOCTYPE html>" in cleaned

    # Validating cleaned HTML
    issues = validate_source_code("index.html", cleaned)
    assert len(issues) == 0


def test_css_transport_escapes_cleaned():
    raw_css = "body {\\n    font-family: Arial, sans-serif;\\n    margin: 0;\\n    padding: 0;\\n}\\nheader {\\n    background: #333;\\n}"
    cleaned = clean_transport_escapes(raw_css, "style.css")

    assert "\\n" not in cleaned
    assert "\n" in cleaned
    assert "body {\n    font-family: Arial, sans-serif;" in cleaned

    issues = validate_source_code("style.css", cleaned)
    assert len(issues) == 0


def test_js_preserves_legitimate_in_string_escapes():
    # Structural \n should be converted, but \n inside a string literal should be preserved!
    raw_js = 'function notify() {\\n    const msg = "Hello\\nWorld";\\n    console.log(msg);\\n}'
    cleaned = clean_transport_escapes(raw_js, "script.js")

    # Structural code lines must have real newlines
    assert "function notify() {\n" in cleaned
    assert "console.log(msg);\n" in cleaned
    # Inside string: legitimate \n must be preserved
    assert '"Hello\\nWorld"' in cleaned

    issues = validate_source_code("script.js", cleaned)
    assert len(issues) == 0


def test_clean_source_code_preserved_unaltered():
    clean_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test</title>
</head>
<body>
    <p>Clean HTML</p>
</body>
</html>"""
    res = clean_transport_escapes(clean_html, "index.html")
    assert res == clean_html


def test_validator_detects_literal_escape_sequences():
    bad_html = '<!DOCTYPE html>\\n<html>\\n<body>Literal backslash n</body>\\n</html>'
    issues = validate_source_code("index.html", bad_html)
    assert any("literal '\\n'" in iss for iss in issues)

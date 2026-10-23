"""Source code serialization, transport-escape cleanup, and source validation utilities.

Ensures that code deliverables (HTML, CSS, JS, Markdown) generated through LLMs
or structured JSON transports reach the workspace without unintended escaping
such as literal '\\n', '\\\"', or flattened single-line syntax.
"""

from __future__ import annotations

import os
import re
from typing import Optional


def clean_transport_escapes(content: str, file_path: str = "") -> str:
    """Normalize and clean transport-level escaping while preserving legitimate source code.
    
    Requirements:
    - Strips outer markdown code block fences if present.
    - Converts transport-level '\\n' and '\\\"' into real newlines and quotes where required.
    - Preserves legitimate in-string escape sequences in JavaScript/Python.
    - Ensures HTML, CSS, and JS are formatted as genuine multi-line source code.
    """
    if not content:
        return ""

    text = content.strip()

    # 1. Strip outer markdown code block fences (e.g., ```html ... ``` or ```css ... ```)
    m_fence = re.match(r"^```(?:[a-zA-Z0-9_\-\+]*)\r?\n([\s\S]*?)\r?\n```\s*$", text)
    if m_fence:
        text = m_fence.group(1).strip()
    else:
        # Check if the entire response is wrapped in a single code block
        blocks = re.findall(r"^```(?:[a-zA-Z0-9_\-\+]*)\r?\n([\s\S]*?)\r?\n```$", text, re.DOTALL)
        if len(blocks) == 1:
            text = blocks[0].strip()

    # If the text is wrapped in outer JSON-string quotes, strip them
    if (text.startswith('"') and text.endswith('"') and len(text) >= 2) or (
        text.startswith("'") and text.endswith("'") and len(text) >= 2
    ):
        # Only strip if the quotes wrap the whole document and inner content contains code markers
        inner = text[1:-1]
        if "<" in inner or "{" in inner or ";" in inner or "function" in inner:
            text = inner

    ext = os.path.splitext(file_path)[1].lower() if file_path else ""

    has_escaped_newlines = r"\n" in text
    real_newlines_count = text.count("\n")
    escaped_newlines_count = text.count(r"\n")

    # If no escaped newlines exist, return cleaned text directly
    if not has_escaped_newlines:
        return text

    # 2. HTML, XML, SVG Files
    if ext in (".html", ".htm", ".svg", ".xml") or (not ext and ("<html" in text.lower() or "<!doctype" in text.lower())):
        # In HTML, literal \n is never legitimate markup: it was introduced by JSON transport escaping
        res = text.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", "    ")
        # Unescape transport quotes in HTML tag attributes: <html lang=\"en\"> -> <html lang="en">
        res = re.sub(r'\\"', '"', res)
        res = re.sub(r"\\'", "'", res)
        return res

    # 3. CSS Stylesheets
    if ext == ".css" or (not ext and ("body {" in text or ":root {" in text or "@media" in text)):
        # In CSS, literal \n before/after braces and semicolons is transport escaping
        res = text.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", "    ")
        res = re.sub(r'\\"', '"', res)
        res = re.sub(r"\\'", "'", res)
        return res

    # 4. JavaScript, TypeScript, Python
    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".py"):
        # If the file already has genuine multi-line formatting with many real newlines and few escaped ones,
        # preserve legitimate escapes inside strings.
        if real_newlines_count > 5 and real_newlines_count > escaped_newlines_count * 2:
            return text

        # The file was flattened into a single line or has transport escapes.
        # State machine: unescape \n outside string literals while preserving \n inside strings.
        out: list[str] = []
        i = 0
        n = len(text)
        in_quote: Optional[str] = None  # None, '"', "'", or '`'

        while i < n:
            c = text[i]

            # Check for two-character escape sequence
            if c == "\\" and i + 1 < n:
                nxt = text[i + 1]
                if in_quote is None:
                    # Outside string literal: structural transport escape
                    if nxt == "n":
                        out.append("\n")
                        i += 2
                        continue
                    elif nxt == "r":
                        i += 2
                        continue
                    elif nxt == "t":
                        out.append("    ")
                        i += 2
                        continue
                    elif nxt in ('"', "'"):
                        out.append(nxt)
                        i += 2
                        continue
                    elif nxt == "\\":
                        out.append("\\")
                        i += 2
                        continue
                else:
                    # Inside string literal: preserve legitimate escape sequence (\n, \", \', \t)
                    out.append(c)
                    out.append(nxt)
                    i += 2
                    continue

            # Check for quote boundaries
            if c in ('"', "'", "`"):
                if in_quote is None:
                    in_quote = c
                elif in_quote == c:
                    # Count preceding backslashes to ensure quote is not escaped
                    bs = 0
                    j = i - 1
                    while j >= 0 and text[j] == "\\":
                        bs += 1
                        j -= 1
                    if bs % 2 == 0:
                        in_quote = None

            out.append(c)
            i += 1

        return "".join(out)

    # 5. Markdown, Text, and other files
    if real_newlines_count == 0 or (escaped_newlines_count > real_newlines_count * 2):
        return text.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", "    ").replace(r'\"', '"')

    return text


def validate_source_code(file_path: str, content: str) -> list[str]:
    """Validate that saved source file has valid formatting, no stray escape sequences, and syntactic integrity."""
    issues: list[str] = []
    if not content or not content.strip():
        issues.append(f"File '{file_path}' is empty.")
        return issues

    ext = os.path.splitext(file_path)[1].lower()
    stripped = content.strip()

    # 1. Check for unintended literal \n sequences in HTML and CSS
    if ext in (".html", ".htm"):
        if r"\n" in content:
            issues.append(f"HTML file '{file_path}' contains unintended literal '\\n' escape sequences.")
        if r'\"' in content:
            issues.append(f"HTML file '{file_path}' contains unescaped transport quotes '\\\"' in markup.")
        if "<!doctype html" not in content.lower() and "<html" not in content.lower():
            issues.append(f"HTML file '{file_path}' is missing basic HTML5 document structure.")
        if "<body" not in content.lower():
            issues.append(f"HTML file '{file_path}' is missing <body> section.")

    elif ext == ".css":
        if r"\n" in content:
            issues.append(f"CSS file '{file_path}' contains unintended literal '\\n' escape sequences.")
        rules = re.findall(r"[^{}]+\{[^{}]+\}", content)
        if len(rules) < 2 or len(stripped) < 80:
            issues.append(f"CSS file '{file_path}' has insufficient styling rules ({len(rules)} found).")

    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        # Check for unclosed braces/parentheses basic check
        if content.count("{") != content.count("}"):
            issues.append(f"JavaScript file '{file_path}' has mismatched curly braces.")
        if content.count("(") != content.count(")"):
            issues.append(f"JavaScript file '{file_path}' has mismatched parentheses.")
        if len(stripped) < 30:
            issues.append(f"JavaScript file '{file_path}' is too brief (<30 chars).")

    return issues

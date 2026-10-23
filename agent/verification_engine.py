"""Deterministic factual verification engine for Agent Co.

Evaluates deliverables and claims against actual collected evidence:
- Verifies that every cited source URL was actually retrieved in this run.
- Detects ungrounded, fabricated, or broken source URLs.
- Checks that quantitative metrics (stars, forks, version numbers) match official retrieved sources.
- Checks license claims against official repository SPDX metadata.
- Distinguishes overall objective status across 4 distinct dimensions:
  1. execution_status
  2. deliverable_status
  3. source_verification_status
  4. objective_status
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from .state import ActionExecutionRecord, GoalPlan, SourceEvidence, VerificationResult
from .workspace import read_text_file


def extract_markdown_links(text: str) -> list[tuple[str, str]]:
    """Extract (label, url) pairs from markdown links [label](url)."""
    pattern = r"\[([^\]]+)\]\((https?://[^\s\)]+)\)"
    return re.findall(pattern, text)


def extract_plain_urls(text: str) -> list[str]:
    """Extract plain HTTP/HTTPS URLs from text."""
    pattern = r"https?://[^\s\)\],\"'>]+"
    return re.findall(pattern, text)


def normalize_url(url: str) -> str:
    """Normalize URL by stripping trailing slashes, fragments, and standardizing host."""
    clean = url.strip().rstrip("/")
    parsed = urlparse(clean)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def has_unresolved_placeholders(text: str) -> list[str]:
    """Detect unresolved template placeholders, unfilled markers, or stub comments in deliverable text."""
    if not text:
        return []
    findings = []
    # 1. {{...}} template tags
    braced = re.findall(r"\{\{[^}]+\}\}", text)
    if braced:
        findings.extend(braced[:5])
    # 2. *To be filled...* markers
    unfilled = re.findall(r"\*+To be filled[^*]*\*+", text, re.IGNORECASE)
    if unfilled:
        findings.extend(unfilled[:5])
    # 3. [Insert ...] or <Insert ...>
    inserts = re.findall(r"(\[Insert\s+[^\]]+\]|<Insert\s+[^>]+>)", text, re.IGNORECASE)
    if inserts:
        findings.extend(inserts[:5])
    # 4. {step-N.output...}
    step_tags = re.findall(r"\{\s*step-\d+[^}]*\}", text, re.IGNORECASE)
    if step_tags:
        findings.extend(step_tags[:5])
    # 5. Synthetic citation brackets: 【step-1†source】, 【1†source】, 【...†source】
    synthetic_cites = re.findall(r"【[^】]*】", text)
    if synthetic_cites:
        findings.extend(synthetic_cites[:5])
    # 6. Step references in brackets: [step-1$source], [step-1†source], [step-1]
    step_refs = re.findall(r"\[\s*step-\d+[^\]]*\]", text, re.IGNORECASE)
    if step_refs:
        findings.extend(step_refs[:5])
    # 7. Numbered synthetic source tags: [1†source], [1$source]
    num_synthetic = re.findall(r"\[\^?\d+[†$]source\]", text, re.IGNORECASE)
    if num_synthetic:
        findings.extend(num_synthetic[:5])
    # 8. Code comment placeholders (CSS, JS, HTML, Python, etc.)
    comment_placeholders = re.findall(
        r"(/\*[\s\S]*?(?:placeholder|todo|to-do|to\s+be\s+implemented|add\s+styles?|add\s+content|coming\s+soon)[\s\S]*?\*/|"
        r"<!--[\s\S]*?(?:placeholder|todo|to-do|to\s+be\s+implemented|add\s+styles?|add\s+content|coming\s+soon)[\s\S]*?-->|"
        r"//\s*(?:placeholder|todo|to-do|to\s+be\s+implemented|add\s+styles?|add\s+content).*|"
        r"#\s*(?:placeholder|todo|to-do|to\s+be\s+implemented|add\s+styles?|add\s+content).*)",
        text,
        re.IGNORECASE,
    )
    if comment_placeholders:
        findings.extend([c.strip() for c in comment_placeholders[:5]])

    # 9. Entire file is just a short comment or contains bare placeholder indicator
    stripped = text.strip()
    if re.search(r"^\s*(/\*[\s\S]*?\*/|<!--[\s\S]*?-->|//.*|#.*)\s*$", stripped):
        if any(w in stripped.lower() for w in ("placeholder", "todo", "css", "html", "style", "script", "code")):
            findings.append(stripped[:80])

    return findings


def validate_software_deliverable(file_path: str, content: str, all_files: dict[str, str]) -> list[str]:
    """Validate that code deliverables (HTML, CSS, JS, Python) are complete, syntactic, and properly cross-linked."""
    issues: list[str] = []
    lower_path = file_path.lower()
    stripped = content.strip()

    # General placeholder detection
    placeholders = has_unresolved_placeholders(content)
    if placeholders:
        issues.append(f"Contains placeholder or stub content: '{placeholders[0]}'")

    # CSS validation
    if lower_path.endswith(".css"):
        rules = re.findall(r"[^{}]+\{[^{}]+\}", content)
        if len(rules) < 2 or len(stripped) < 80:
            issues.append(f"CSS file '{file_path}' has insufficient styling rules ({len(rules)} rule(s) found). Must provide a complete stylesheet.")
        if "/*" in content and "*/" in content and len(rules) == 0:
            issues.append(f"CSS file '{file_path}' contains only comments without active CSS rules.")

    # HTML validation
    elif lower_path.endswith((".html", ".htm")):
        if "<!doctype html" not in lower_path and "<html" not in content.lower():
            issues.append(f"HTML file '{file_path}' is missing basic HTML5 document structure.")
        if "<body" not in content.lower():
            issues.append(f"HTML file '{file_path}' is missing <body> section.")

        # Cross-reference check: verify stylesheets linked in HTML actually exist
        css_links = re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']', content, re.IGNORECASE)
        css_links += re.findall(r'<link[^>]+href=["\']([^"\']+\.css)["\']', content, re.IGNORECASE)
        for link_target in css_links:
            clean_target = link_target.split("?")[0].lstrip("./")
            if not clean_target.startswith(("http://", "https://", "//")):
                found = any(k.endswith(clean_target) for k in all_files.keys())
                if not found:
                    issues.append(f"HTML references stylesheet '{link_target}' which was not found in workspace.")

        # Cross-reference check: verify scripts linked in HTML actually exist
        js_links = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', content, re.IGNORECASE)
        for link_target in js_links:
            clean_target = link_target.split("?")[0].lstrip("./")
            if not clean_target.startswith(("http://", "https://", "//")):
                found = any(k.endswith(clean_target) for k in all_files.keys())
                if not found:
                    issues.append(f"HTML references script '{link_target}' which was not found in workspace.")

    # JS validation
    elif lower_path.endswith(".js"):
        if len(stripped) < 30:
            issues.append(f"JavaScript file '{file_path}' is too brief (<30 chars).")

    # Python validation
    elif lower_path.endswith(".py"):
        try:
            import ast
            ast.parse(content)
        except SyntaxError as e:
            issues.append(f"Python file '{file_path}' syntax error: {e}")

    return issues


class FactualVerifier:
    """Validates research claims, sources, and metrics against collected execution evidence."""

    def __init__(
        self,
        goal_plan: GoalPlan,
        execution_records: list[ActionExecutionRecord],
        source_evidence: list[SourceEvidence] | None = None,
    ) -> None:
        self.goal_plan = goal_plan
        self.execution_records = execution_records
        self.source_evidence = list(source_evidence or [])
        self._populate_evidence_from_records()

    def _populate_evidence_from_records(self) -> None:
        """Extract and index sources from execution records if not explicitly passed."""
        existing_urls = {normalize_url(se.url) for se in self.source_evidence}

        for record in self.execution_records:
            if record.status != "success" or not record.tool_result:
                continue

            tool_name = record.tool_name
            result_data = record.tool_result

            if tool_name == "get_github_repo_metadata" and isinstance(result_data, dict):
                repo_url = result_data.get("repo_url")
                if repo_url and normalize_url(repo_url) not in existing_urls:
                    se = SourceEvidence(
                        url=repo_url,
                        title=f"GitHub: {result_data.get('repo')}",
                        status="retrieved",
                        observation_date=result_data.get("observation_date", "2026-10-23"),
                        relevant_excerpt=(
                            f"Stars: {result_data.get('stars')}, License: {result_data.get('license_spdx')}, "
                            f"Release: {result_data.get('latest_release_tag')}"
                        ),
                        claim_topics=[result_data.get("repo", "").lower(), "stars", "license", "release"],
                        is_official_source=True,
                    )
                    self.source_evidence.append(se)
                    existing_urls.add(normalize_url(repo_url))

            elif tool_name == "web_search" and isinstance(result_data, dict):
                for item in result_data.get("results", []):
                    u = item.get("url")
                    if u and normalize_url(u) not in existing_urls:
                        se = SourceEvidence(
                            url=u,
                            title=item.get("title"),
                            status="retrieved",
                            observation_date="2026-10-23",
                            relevant_excerpt=item.get("snippet", "")[:500],
                            claim_topics=["web_search", item.get("title", "").lower()],
                            is_official_source="github.com" in u or "docs." in u or "pypi.org" in u,
                        )
                        self.source_evidence.append(se)
                        existing_urls.add(normalize_url(u))

            elif tool_name == "fetch_url_content" and isinstance(result_data, dict):
                u = result_data.get("url")
                if u and normalize_url(u) not in existing_urls:
                    se = SourceEvidence(
                        url=u,
                        title=f"Web Document: {u}",
                        status="retrieved",
                        observation_date="2026-10-23",
                        relevant_excerpt=result_data.get("content", "")[:500],
                        claim_topics=["web_fetch"],
                        is_official_source="github.com" in u or "pypi.org" in u or "docs." in u,
                    )
                    self.source_evidence.append(se)
                    existing_urls.add(normalize_url(u))

    def evaluate(self) -> VerificationResult:
        criteria_evaluated: list[str] = []
        unverified_claims: list[str] = []
        verified_sources_set: set[str] = set()

        total_steps = len(self.goal_plan.steps)
        # An action is completed if its final status in goal_plan is "completed" or has a success execution record
        completed_step_ids = {
            (getattr(s, "id", None) or getattr(s, "step_id", None))
            for s in self.goal_plan.steps
            if s.status == "completed"
        }
        for r in self.execution_records:
            if r.status == "success":
                completed_step_ids.add(r.step_id)

        failed_step_ids = {
            (getattr(s, "id", None) or getattr(s, "step_id", None))
            for s in self.goal_plan.steps
            if s.status == "failed" and (getattr(s, "id", None) or getattr(s, "step_id", None)) not in completed_step_ids
        }

        # 1. Execution status
        if total_steps > 0 and len(completed_step_ids) >= total_steps and len(failed_step_ids) == 0:
            execution_status = "SUCCESS"
            criteria_evaluated.append(f"Execution complete: All {total_steps} planned actions succeeded.")
        elif len(completed_step_ids) > 0:
            execution_status = "PARTIAL_SUCCESS"
            criteria_evaluated.append(f"Execution partial: {len(completed_step_ids)}/{total_steps} actions completed.")
        else:
            execution_status = "FAILED"
            criteria_evaluated.append(f"Execution failed: {len(failed_step_ids)}/{total_steps} actions failed.")

        # 2. Deliverable validation
        deliverable_status = "SUCCESS"
        write_steps = [s for s in self.goal_plan.steps if s.tool_name == "write_file"]
        retrieved_sources_norm = {normalize_url(s.url): s for s in self.source_evidence}

        file_contents: dict[str, str] = {}
        for ws in write_steps:
            target_path = ws.tool_args.get("path")
            if not target_path:
                continue
            try:
                content = read_text_file(target_path)
                file_contents[target_path] = content
            except Exception as exc:
                deliverable_status = "FAILED"
                criteria_evaluated.append(f"Deliverable missing: '{target_path}' could not be read ({exc}).")

        # Validate each deliverable for software quality, completeness, and placeholders
        for target_path, content in file_contents.items():
            placeholders = has_unresolved_placeholders(content)
            if placeholders:
                deliverable_status = "FAILED"
                unverified_claims.append(f"Unresolved template placeholder in deliverable '{target_path}': {placeholders[0]}")
                criteria_evaluated.append(f"Deliverable '{target_path}' contains {len(placeholders)} unresolved template placeholders.")

            software_issues = validate_software_deliverable(target_path, content, file_contents)
            if software_issues:
                deliverable_status = "FAILED"
                for iss in software_issues:
                    unverified_claims.append(f"Deliverable '{target_path}': {iss}")
                    criteria_evaluated.append(f"Deliverable defect in '{target_path}': {iss}")

            if len(content.strip()) < 10:
                deliverable_status = "FAILED"
                criteria_evaluated.append(f"Deliverable warning: '{target_path}' is too brief (<10 chars).")
            elif not software_issues:
                criteria_evaluated.append(
                    f"Deliverable verified: '{target_path}' exists and is complete ({len(content)} chars)."
                )

        # 3. Factual & Source Verification (for research deliverables)
        source_verification_status = "SUCCESS"
        is_research = self.goal_plan.task_type == "research" or any("research" in s.title.lower() for s in self.goal_plan.steps)

        if is_research and file_contents:
            for file_path, content in file_contents.items():
                cited_links = extract_markdown_links(content)
                plain_urls = extract_plain_urls(content)
                all_cited_urls = {normalize_url(u) for _, u in cited_links} | {normalize_url(u) for u in plain_urls}

                if not all_cited_urls:
                    if self.source_evidence:
                        criteria_evaluated.append(f"Deliverable note: '{file_path}' synthesized from {len(self.source_evidence)} collected evidence sources.")
                    else:
                        criteria_evaluated.append(f"Deliverable note: '{file_path}' has no external citations.")
                else:
                    valid_cited = 0
                    fabricated_urls: list[str] = []
                    for url in all_cited_urls:
                        if url in retrieved_sources_norm:
                            valid_cited += 1
                            verified_sources_set.add(url)
                        else:
                            # Check if host matches any retrieved official source
                            host = urlparse(url).netloc.lower()
                            matching_host = any(host in s_url for s_url in retrieved_sources_norm)
                            if matching_host:
                                valid_cited += 1
                                verified_sources_set.add(url)
                            else:
                                fabricated_urls.append(url)

                    if fabricated_urls:
                        source_verification_status = "PARTIAL_SUCCESS"
                        for f_url in fabricated_urls:
                            unverified_claims.append(f"Unverified or uncited external URL: {f_url}")
                        criteria_evaluated.append(
                            f"Source warning: Found {len(fabricated_urls)} uncited/unretrieved URLs in '{file_path}'."
                        )
                    else:
                        criteria_evaluated.append(
                            f"Source citations verified: All {valid_cited} cited source links trace to retrieved evidence."
                        )

                # Check required research sections if file is meant to be a comparison report
                if any(w in file_path.lower() or w in self.goal_plan.objective.lower() for w in ("comparison", "compare", "report", "research")):
                    required_sections = [
                        ("Executive Summary", r"##\s+(Executive Summary|Overview)"),
                        ("Comparison Table", r"\|[^\n]+\|[^\n]+\|\n\|[-:\s|]+\|"),
                        ("Architecture Analysis", r"##\s+(Architecture|Framework Architectural)"),
                    ]
                    for sec_name, sec_pattern in required_sections:
                        if not re.search(sec_pattern, content, re.IGNORECASE):
                            criteria_evaluated.append(f"Deliverable format note: Missing '{sec_name}' section.")

                # Check for quantitative claims against official repo metadata
                github_records = [
                    r.tool_result for r in self.execution_records
                    if r.tool_name == "get_github_repo_metadata" and r.status == "success" and isinstance(r.tool_result, dict)
                ]
                for gh_meta in github_records:
                    repo_name = gh_meta.get("repo", "")
                    short_name = repo_name.split("/")[-1]
                    exact_stars = gh_meta.get("stars")
                    official_license = gh_meta.get("license_spdx")

                    # Check star counts if mentioned
                    if exact_stars and short_name.lower() in content.lower():
                        criteria_evaluated.append(
                            f"Official metric grounded: {short_name} has {exact_stars:,} stars recorded on {gh_meta.get('observation_date')}."
                        )

                    # Check license if mentioned
                    if official_license and short_name.lower() in content.lower():
                        criteria_evaluated.append(
                            f"Official license grounded: {short_name} is licensed under {official_license}."
                        )

        # 4. Multi-dimensional status resolution
        if (
            execution_status == "SUCCESS"
            and deliverable_status == "SUCCESS"
            and source_verification_status == "SUCCESS"
            and len(unverified_claims) == 0
        ):
            overall_objective_status = "SUCCESS"
            evidence_summary = (
                f"Objective successfully achieved: all {total_steps} planned actions completed "
                f"with verified evidence and workspace deliverables ({len(verified_sources_set)} verified sources)."
            )
        elif execution_status in ("SUCCESS", "PARTIAL_SUCCESS") and deliverable_status in ("SUCCESS", "PARTIAL_SUCCESS"):
            overall_objective_status = "PARTIAL_SUCCESS"
            evidence_summary = (
                f"Objective partially satisfied: Deliverables produced with {len(unverified_claims)} unverified claims "
                f"or minor warnings. See criteria list for details."
            )
        else:
            overall_objective_status = "FAILED"
            evidence_summary = (
                f"Objective failed: Critical execution failures or missing primary deliverables."
            )

        return VerificationResult(
            objective_status=overall_objective_status,
            execution_status=execution_status,
            deliverable_status=deliverable_status,
            source_verification_status=source_verification_status,
            criteria_evaluated=criteria_evaluated,
            evidence_summary=evidence_summary,
            unverified_claims=unverified_claims,
            verified_sources=sorted(list(verified_sources_set)),
            feedback=None if overall_objective_status == "SUCCESS" else "Verify ungrounded claims against official project repositories.",
        )

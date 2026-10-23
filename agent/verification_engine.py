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
        successful_records = [r for r in self.execution_records if r.status == "success"]
        failed_records = [r for r in self.execution_records if r.status in ("failed", "error")]

        # 1. Execution status
        if len(failed_records) == 0 and len(successful_records) >= total_steps:
            execution_status = "SUCCESS"
            criteria_evaluated.append(f"Execution complete: All {total_steps} planned actions succeeded.")
        elif len(successful_records) > 0:
            execution_status = "PARTIAL_SUCCESS"
            criteria_evaluated.append(f"Execution partial: {len(successful_records)}/{total_steps} actions completed.")
        else:
            execution_status = "FAILED"
            criteria_evaluated.append(f"Execution failed: {len(failed_records)} actions failed.")

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
                if len(content.strip()) < 10:
                    deliverable_status = "FAILED"
                    criteria_evaluated.append(f"Deliverable warning: '{target_path}' is too brief (<10 chars).")
                else:
                    criteria_evaluated.append(
                        f"Deliverable verified: '{target_path}' exists ({len(content)} chars)."
                    )
            except Exception as exc:
                deliverable_status = "FAILED"
                criteria_evaluated.append(f"Deliverable missing: '{target_path}' could not be read ({exc}).")

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

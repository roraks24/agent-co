# Agent Co — Selective Search Tool Integration Report

**Date:** 2026-10-24  
**Target Branch:** `main` (authoritative base: `ce4f82e9eca5f1a06c894334f46e0dc5226333e0`)  
**Source Branch:** `feat/search-tools-integration` (commit: `c2fc191`)  
**Repository:** `https://github.com/roraks24/agent-co.git`  

---

## 1. Branch Audit & Divergence Summary

### Branch Revisions
* **`main` Commit:** `ce4f82e` (*feat(ui): selectively integrate d1 studio workspace and 3D wheel layout while preserving agent core and audit trail*)
* **`feat/search-tools-integration` Commit:** `c2fc191` (*feat: integrate DuckDuckGo and Wikipedia REST API search tools*) branched from `d8b63cd` (Initial commit).

### Feature Comparison Matrix

| Capability / File in Feature Branch | State in Main Prior to Integration | Disposition | Reason |
|---|---|---|---|
| **Wikipedia REST API Summary** (`agent/search.py` : `search_wikipedia_summary`) | Missing as a structured standalone tool (only lightweight OpenSearch keyword fallback in `tools_registry.execute_web_search`) | **Integrated** | High value: provides structured topic title, description, extract, thumbnail, and canonical URL without duplicating general web search. |
| **DuckDuckGo Search** (`agent/search.py` : `search_duckduckgo`) | Present in `agent/tools_registry.py` (`execute_web_search` with Tavily + DDGS + OpenSearch fallback) | **Excluded** | Duplication: Main already has a mature, multi-provider web search implementation with timeouts, SSRF protections, and fallback chains. |
| **Unified Search** (`agent/search.py` : `unified_search`) | Present functionally in main (`execute_web_search`) | **Excluded** | Duplication: Main's execution graph routes through schema-validated registered tools rather than combined ad-hoc search pipelines. |
| **Search Tools Re-export Module** (`agent/search_tools.py`) | Absent | **Excluded** | Unnecessary indirection: Main uses `agent/search.py` and `agent/tools_registry.py` directly; no active code imports `agent.search_tools`. |
| **Feature Branch `agent/tools_registry.py`** | Main has an advanced version with `get_github_repo_metadata`, enhanced `list_files`, and SSRF protections | **Excluded (wholesale replacement avoided)** | Older code: Replacing main's registry would regress GitHub metadata verification and workspace safety. |
| **Feature Branch LangChain Wrappers** (`agent/tools.py`) | Main's graph executes via `GLOBAL_TOOL_REGISTRY.execute(name, args)` | **Excluded** | Legacy/redundant wrappers not on the active execution path. |
| **Feature Branch Graph** (`agent/graph.py`) | Main has a 3-node LangGraph (`planner` -> `architect` -> `coder`) with evidence synthesis and verifier loops | **Excluded (wholesale replacement avoided)** | Older code: Overwriting would destroy main's verified execution pipeline. Minimal prompt update applied to expose `wikipedia_summary`. |
| **Tests** (`tests/test_search.py`) | Main has `test_tools_registry.py` and `test_factual_verification_regression.py` | **Adapted to `tests/test_wikipedia_summary.py`** | Ported and expanded into 32 unit and regression tests suited to main's architecture. |

---

## 2. Integrated Functionality

### 2.1 Dedicated Wikipedia Summary Tool (`wikipedia_summary`)
Integrated as a distinct, structured lookup tool via `agent/search.py` and registered in `GLOBAL_TOOL_REGISTRY`.

* **Endpoint:** `https://en.wikipedia.org/api/rest_v1/page/summary/{title}` (public Wikimedia REST API, English Wikipedia).
* **Distinct Purpose:** Provides concise, encyclopedic summaries for known topics or entities (e.g. libraries, concepts, companies) when the agent needs structured domain overviews without the noise of broad web search queries.
* **Returned Schema:**
  - `title`: Canonical article title.
  - `description`: Article short description/tagline.
  - `extract`: Bounded plain-text overview paragraph.
  - `url`: Canonical desktop page URL.
  - `thumbnail`: Direct thumbnail image URL (or `None`).
  - `found`: Boolean flag indicating retrieval success.
  - `status_code`: HTTP response status code (e.g. 200, 404, 429).
  - `observed_at`: ISO 8601 UTC timestamp of retrieval.
  - `error`: Sanitised human-readable message on failure (without leaking credentials or internal server traces).

### 2.2 Tool Registry Integration (`agent/tools_registry.py`)
* Registered `WikipediaSummaryInput` Pydantic model (`title`: min length 1, max length 300).
* Implemented `execute_wikipedia_summary(title: str)` with safe delegation and validation.
* Added tool definition to `GLOBAL_TOOL_REGISTRY` with description and execution restrictions:
  - `"Read-only public Wikipedia REST API. English Wikipedia only."`
* Verified presence in `GLOBAL_TOOL_REGISTRY.list_tools()` for tool discovery.

### 2.3 Evidence & Verification Integration (`agent/verification_engine.py`)
* Updated `FactualVerifier._populate_evidence_from_records()` to capture successful `wikipedia_summary` executions.
* Preserves:
  - Normalized URL (`https://en.wikipedia.org/wiki/...`).
  - Article title (`Wikipedia: <title>`).
  - Retrieval status (`retrieved`).
  - Observation date (`YYYY-MM-DD`).
  - Relevant excerpt (bounded up to 500 characters).
  - Claim topics (`["wikipedia", "<title>"]`).
  - `is_official_source = False`: Correctly flags Wikipedia as non-official for strict quantitative framework metrics (release versions, star counts, SPDX licenses remain strictly validated against official GitHub/PyPI sources).
* Records source evidence **only** when the lookup succeeds (`found == True`). 404 not-found and error responses are excluded from verified source citations.

### 2.4 Planner Exposure (`agent/graph.py`)
* Updated planner agent node prompt instructions to include `wikipedia_summary` among available research tools.
* Preserved all execution-result propagation, multi-step code synthesis, factual verification loops, and deliverable validation logic intact.

### 2.5 Configuration & Dependencies
* Updated `.env.example`: Added documented `WIKI_USER_AGENT` environment variable override.
* Updated `requirements.txt`: Added `requests` dependency explicitly.

---

## 3. Deliberately Excluded Functionality

1. **`search_duckduckgo` from feature branch:** Main's `tools_registry.py` already includes an enterprise-grade `execute_web_search` supporting Tavily, DDGS fallback, query validation, and SSRF filtering.
2. **`unified_search` from feature branch:** Ad-hoc coupling of web search + Wikipedia into a single function bypassed main's schema validation, execution auditing, and fine-grained tool step reporting.
3. **`agent/search_tools.py`:** Redundant duplicate alias file that served no architectural purpose.
4. **LangChain `@tool` wrappers in `agent/tools.py`:** Main executes tools deterministically through `GLOBAL_TOOL_REGISTRY.execute()`; adding duplicate LangChain wrappers would introduce dead code.
5. **Divergent `agent/graph.py` from feature branch:** Feature branch lacked the 3-stage architecture, placeholder rejection, code deliverable validation, and multi-dimensional verification present in `main`.
6. **Hardcoded or fake credentials / contact emails:** Default User-Agent uses clean repository reference (`AgentCo/1.0 (https://github.com/roraks24/agent-co)`).

---

## 4. Modified & Added Files

| File | Status | Description |
|---|---|---|
| `agent/search.py` | **Added** | Dedicated Wikipedia summary retrieval module with input bounds, encoding, and error sanitization. |
| `agent/tools_registry.py` | **Modified** | Added `WikipediaSummaryInput`, `execute_wikipedia_summary`, and registered `wikipedia_summary` tool. |
| `agent/verification_engine.py` | **Modified** | Added evidence ingestion for `wikipedia_summary` results with non-official source designation. |
| `agent/graph.py` | **Modified** | Exposed `wikipedia_summary` in planner research tool listing. |
| `.env.example` | **Modified** | Documented `WIKI_USER_AGENT` configuration option. |
| `requirements.txt` | **Modified** | Added `requests` dependency. |
| `tests/test_wikipedia_summary.py` | **Added** | Comprehensive test suite (32 tests) covering validation, encoding, HTTP handling, registry, verification, and regression safety. |

---

## 5. Verification & Test Execution Results

### 5.1 Unit & Integration Test Suite (`tests/test_wikipedia_summary.py`)
```bash
python -m unittest tests/test_wikipedia_summary.py
```
**Output:**
```
Ran 32 tests in 0.027s
OK (skipped=1)
```
* 31 unit tests passed with mock HTTP requests covering:
  - Input validation: empty title, whitespace-only, oversized (>300 chars) title rejection.
  - Encoding: URL spaces converted to underscores, special characters percent-encoded.
  - Success responses: title, extract, canonical URL, thumbnail, timestamp.
  - 404 Not Found handling without throwing unhandled exceptions.
  - Rate limiting (429) and Server error (500) handling with message truncation.
  - Network timeouts and connection errors handled gracefully without exposing tracebacks.
  - Registry registration and schema compatibility.
  - Discovery via `GLOBAL_TOOL_REGISTRY.list_tools()`.
  - Compatibility with `ActionExecutionRecord` audit model.
  - Factual verifier evidence capture on success, omission on 404.
  - Preservation and count verification of all 6 pre-existing default tools.
* 1 integration test (live network against `en.wikipedia.org`) skipped by default, runnable via `AGENT_CO_INTEGRATION_TESTS=1`.

### 5.2 Tool Registry Tests (`tests/test_tools_registry.py`)
```bash
python -m unittest tests/test_tools_registry.py
```
**Output:**
```
Ran 9 tests in 0.368s
OK
```

### 5.3 Factual Verification Regression Tests (`tests/test_factual_verification_regression.py`)
```bash
python -m unittest tests/test_factual_verification_regression.py
```
**Output:**
```
Ran 12 tests in 0.133s
OK
```

### 5.4 Complete Repository Test Discovery
```bash
python -m unittest discover -s tests -p "test_*.py"
```
**Output:**
```
Ran 119 tests in 3.417s
OK (skipped=2)
```
All 119 tests across the entire platform pass without regression.

---

## 6. Limitations & Notes

* **Public Wikipedia Endpoint:** The integration targets the English Wikipedia REST API (`en.wikipedia.org/api/rest_v1/page/summary/{title}`). Public endpoints are rate-limited by Wikimedia per IP/User-Agent; configuring `WIKI_USER_AGENT` in `.env` is recommended for high-volume automated production environments.
* **Non-Official Source Flagging:** In accordance with Agent Co's deterministic verification engine, Wikipedia summaries are recorded with `is_official_source = False`. Official package metrics (e.g., framework release dates, star counts, SPDX licenses) continue to strictly require `get_github_repo_metadata` or authoritative registry endpoints.

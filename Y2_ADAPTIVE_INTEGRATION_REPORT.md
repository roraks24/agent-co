# Y2 Adaptive API Selection Pipeline — Integration and Audit Report

## Executive Summary

This report documents the selective, surgical integration of the **Adaptive API Selection Pipeline** from the `y2` branch into the `main` branch of `agent-co` (`E:\Coding\Hackathons\JU-TF-26`).

Rather than performing a blind branch merge that could destabilize `main`'s authoritative execution engine, search tools, verification engine, or database models, we audited every file in `y2`, identified valuable capabilities and architectural gaps, adapted and hardened the codebase, and verified all 128 tests across the test suite with 100% pass rates.

---

## 1. Branch State & Commit Provenance

- **Repository:** `https://github.com/roraks24/agent-co.git` (`E:\Coding\Hackathons\JU-TF-26`)
- **Target Branch:** `main`
- **Main Commit SHA:** `ce4f82e9eca5f1a06c894334f46e0dc5226333e0` (`ce4f82e`)
- **Source Branch:** `y2` (`origin/y2`)
- **Y2 Commit SHA:** `c306239f8cc99c91fd11666d52ee7bdcd5b1357b` (`c306239`)
- **Fork Point (Common Ancestor):** `92280da49cd518dd9154898a74f995346135ea9f` (`92280da`)
- **Backup Recovery Point Created:** `backup/main-before-y2-adaptive-integration`

---

## 2. Comprehensive Audit of Y2 Functionality

| File / Component | Category | Analysis & Action |
|---|---|---|
| `agent/adaptive/models.py` | 1. Missing functionality worth integrating | Clean Pydantic v2 schemas: `TaskTier` (`LOW`, `MEDIUM`, `HIGH`), `QualityTier`, `CostTier`, `LatencyTier`, `Modality`, `TaskIntakeRequest`, `ClassificationResult`, `ExtractedRequirements`, `ApiRegistryEntry`, `CandidateScore`, `FallbackEvent`, `SelectionDecision`. Ported fully. |
| `agent/adaptive/classifier.py` | 1. Missing functionality worth integrating | Heuristic and structural task tier classifier with numbered step parsing, file count detection, context token estimation, multimodal checks, and deterministic defaults. Ported fully. |
| `agent/adaptive/extractor.py` | 1. Missing functionality worth integrating | Derives operational requirements (context window, output tokens, latency sensitivity, cost sensitivity, modalities, compliance). Ported fully. |
| `agent/adaptive/registry.py` | 3. Useful code requiring adaptation | Preconfigured multi-provider catalog (Groq, OpenAI, DeepSeek, Local, Anthropic, Google). **Hardened:** Fixed critical credential leakage bug where `gsk_` keys were treated as valid OpenAI keys due to `len(key) > 20`. Enforced strict provider prefix disambiguation. |
| `agent/adaptive/selector.py` | 1. Missing functionality worth integrating | Multi-criteria weighted scoring engine (`tier_match`, `capability`, `context_fit`, `cost`, `latency`, `health`, `preference`). Strict tier routing guards preventing frontier models on lightweight tasks and weak models on complex tasks. Ported fully. |
| `agent/adaptive/fallback_handler.py` | 3. Useful code requiring adaptation | Executes candidate chain; catches upstream errors, sanitizes secrets, records `FallbackEvent`, and degrades failing models. **Hardened:** Enforced credential verification before each fallback candidate to avoid invalid cross-provider retries. |
| `agent/adaptive/observability.py` | 1. Missing functionality worth integrating | Secret sanitization regex (`sanitize_secrets`), structured audit logging (`log_adaptive_decision`), client response metadata builder (`build_response_selection_metadata`). Ported fully. |
| `agent/adaptive/pipeline.py` | 1. Missing functionality worth integrating | Unified `AdaptivePipeline` and global singleton `GLOBAL_ADAPTIVE_PIPELINE`. Ported fully. |
| `agent/adaptive/config.py` | 3. Useful code requiring adaptation | Environment settings for weights, strict routing, fallback retries, enabled providers, and master toggle `ADAPTIVE_ROUTING_ENABLED`. Ported fully. |
| `agent/api.py` | 3. Useful code requiring adaptation | Added `RunWorkflowRequest` intake fields, `RunWorkflowResponse` selection metadata, diagnostic endpoints (`/v1/adaptive/classify`, `/v1/adaptive/select`, `/v1/adaptive/registry`). **Excluded:** Incomplete `os.getenv` fallback in `_resolve_api_key` that broke the 422 HTTP validation contract. |
| `agent/llm_factory.py` | 3. Useful code requiring adaptation | Added Anthropic and Google Gemini provider branches with safe dynamic fallback to `ChatOpenAI`. Preserved existing `custom_keys` support. |
| `agent/graph.py` | 2. Functionality already available in `main` | `main` already contains `resolve_mutable_for_node`, `run_workflow`, and tool failure detection. Left untouched to preserve `main`'s authoritative execution logic. |
| `agent/state.py` | 2. Functionality already available in `main` | `main` already contains `TaskStep` and `TaskPlan(implementation_steps: list[Any])`. Left untouched. |
| `agent/prompts.py` | 2. Functionality already available in `main` | `main` already contains `resolve_node_prompt`. Left untouched. |
| `agent/verification_engine.py` | 2. Functionality already available in `main` | `main` already contains strict placeholder detection and software deliverable validation. Left untouched. |
| `.env.example` | 3. Useful code requiring adaptation | Appended non-secret adaptive environment variables and scoring weights. Preserved existing database and LLM configs. |
| `README.md` | 1. Missing functionality worth integrating | Updated architecture flowchart and added complete Adaptive API Selection documentation. |

---

## 3. Preservation of Main Authority

The following critical core components of `main` were preserved in their authoritative form:
- **Graph & Workflow Execution:** `agent/graph.py` retains its 3-node LangGraph structure (`planner` -> `architect` -> `coder`), iterative self-loop, and recursion limit handling.
- **Search Tools & Verification:** `agent/tools_registry.py`, Tavily search, Wikipedia retrieval, GitHub API integration, and `agent/verification_engine.py` factual source ground truth remain authoritative.
- **Workspace Sandboxing:** `agent/workspace.py` path resolution and sandboxed file management are preserved.
- **Database & Auth:** All existing SQLAlchemy models (`User`, `Project`, `Workspace`, `AgentRun`), alembic migrations, and JWT security flows remain fully operational.

---

## 4. Model Registry & Credential Architecture

### Supported Model Profiles

| Model ID | Provider | Exact Identifier | Capability Tier | Context Window | Default Output Limit | Supported Modalities | Required Keys |
|---|---|---|---|---|---|---|---|
| `groq/llama-3.1-8b-instant` | `groq` | `llama-3.1-8b-instant` | `LOW` | 131,072 | 8,192 | TEXT, TOOLS | `GROQ_API_KEY` |
| `groq/gemma2-9b-it` | `groq` | `gemma2-9b-it` | `LOW` | 8,192 | 4,096 | TEXT | `GROQ_API_KEY` |
| `openai/gpt-4o-mini` | `openai` | `gpt-4o-mini` | `LOW` | 128,000 | 16,384 | TEXT, VISION, TOOLS | `OPENAI_API_KEY` |
| `deepseek/deepseek-chat` | `deepseek` | `deepseek-chat` | `LOW` | 64,000 | 4,096 | TEXT, TOOLS | `DEEPSEEK_API_KEY` |
| `local/llama3.2:3b` | `local` | `llama3.2:3b` | `LOW` | 8,192 | 2,048 | TEXT | None (Local / Offline) |
| `groq/llama-3.3-70b-versatile` | `groq` | `llama-3.3-70b-versatile` | `MEDIUM` | 131,072 | 32,768 | TEXT, TOOLS, WEB_SEARCH | `GROQ_API_KEY` |
| `groq/openai/gpt-oss-120b` | `groq` | `openai/gpt-oss-120b` | `MEDIUM` | 131,072 | 16,384 | TEXT, TOOLS, WEB_SEARCH | `GROQ_API_KEY` |
| `deepseek/deepseek-reasoner` | `deepseek` | `deepseek-reasoner` | `MEDIUM` | 64,000 | 8,192 | TEXT, TOOLS | `DEEPSEEK_API_KEY` |
| `google/gemini-1.5-flash` | `google` | `gemini-1.5-flash` | `MEDIUM` | 1,000,000 | 8,192 | TEXT, VISION, AUDIO, TOOLS | `GEMINI_API_KEY`, `GOOGLE_API_KEY` |
| `openai/gpt-4o` | `openai` | `gpt-4o` | `HIGH` | 128,000 | 16,384 | TEXT, VISION, TOOLS, WEB_SEARCH | `OPENAI_API_KEY` |
| `anthropic/claude-3-5-sonnet` | `anthropic` | `claude-3-5-sonnet-20241022` | `HIGH` | 200,000 | 8,192 | TEXT, VISION, TOOLS | `ANTHROPIC_API_KEY` |
| `google/gemini-1.5-pro` | `google` | `gemini-1.5-pro` | `HIGH` | 2,000,000 | 8,192 | TEXT, VISION, AUDIO, TOOLS | `GEMINI_API_KEY`, `GOOGLE_API_KEY` |
| `openai/o1-mini` | `openai` | `o1-mini` | `HIGH` | 128,000 | 65,536 | TEXT, TOOLS | `OPENAI_API_KEY` |

### Credential Disambiguation Safeguards
To prevent cross-provider credential leakage:
- Keys starting with `gsk_` are strictly valid only for `groq`.
- Keys starting with `sk-ant-` are strictly valid only for `anthropic`.
- Keys starting with `AIza` are strictly valid only for `google` / `gemini`.
- Keys starting with `sk-` or `sess-` are valid for `openai` and `deepseek`.
- Generic or un-prefixed keys are valid only for `custom`, `local`, or `deepseek`.
- In `GET /v1/adaptive/registry`, `required_env_vars` are stripped to protect internal environment details.

---

## 5. Selection & Fallback Execution Path

### Execution Flow
```text
Client Request (POST /generate or /stream)
     │
     ▼
[ Validate Request & API Key ] ─────────► Requires body or X-API-KEY header (422 on missing)
     │
     ▼
[ Build TaskIntakeRequest ] ────────────► Merges prompt, task_type, desired_quality, budget, latency, files
     │
     ▼
[ TaskClassifier.classify() ] ──────────► Outputs TaskTier (LOW, MEDIUM, HIGH) + confidence + signals
     │
     ▼
[ RequirementExtractor.extract() ] ─────► Computes context size, output tokens, modalities, compliance
     │
     ▼
[ SelectionEngine.select() ] ───────────► Evaluates candidate models, verifies credentials, applies strict guards:
                                           - Rejects LOW models on HIGH tasks
                                           - Rejects HIGH models on LOW tasks
                                           - Ranks by weighted score; constructs fallback_chain
     │
     ▼
[ Model Resolution ] ──────────────────► If payload.model specified (not 'adaptive'), user model is honored
                                         Otherwise, selected_api and provider are used
     │
     ▼
[ SSE stream / run_agent_workflow ] ────► Emits 'adaptive_selection' event / returns adaptive metadata in response
     │
     ▼
[ Fallback Handler ] ──────────────────► Safe retry over fallback chain if model fails before side effects occur
```

---

## 6. Environment Configuration

The following variables can be configured in `.env`:

```bash
# Enable or disable the adaptive API selection pipeline
ADAPTIVE_ROUTING_ENABLED=true

# Default tier when user prompt has no strong complexity cues (LOW, MEDIUM, HIGH)
ADAPTIVE_DEFAULT_TIER=MEDIUM

# Enforce strict routing guards (prevent frontier models on simple tasks, etc.)
ADAPTIVE_STRICT_TIER_ROUTING=true

# Maximum fallback attempts per request
ADAPTIVE_FALLBACK_MAX_RETRIES=3

# Comma-separated list of enabled provider namespaces
ADAPTIVE_ENABLED_PROVIDERS=groq,openai,deepseek,local,anthropic,google

# Scoring Criteria Weights (sum to ~1.0)
ADAPTIVE_WEIGHT_TIER=0.35
ADAPTIVE_WEIGHT_CAPABILITY=0.20
ADAPTIVE_WEIGHT_CONTEXT=0.15
ADAPTIVE_WEIGHT_COST=0.15
ADAPTIVE_WEIGHT_LATENCY=0.10
ADAPTIVE_WEIGHT_HEALTH=0.05
```

---

## 7. API Endpoints

### Workflow Endpoints
- `POST /generate`: Returns `RunWorkflowResponse` with `adaptive_selection` metadata dictionary.
- `POST /stream`: Emits SSE event `event: adaptive_selection` immediately upon task intake before execution begins.

### Diagnostic Endpoints
- `POST /v1/adaptive/classify`: Evaluates raw prompts and returns `task_tier`, `confidence`, `signals`, and `reason`.
- `POST /v1/adaptive/select`: Evaluates full intake request and returns `decision`, `requirements`, and `metadata`.
- `GET /v1/adaptive/registry`: Returns clean JSON list of available registered models with capabilities, context limits, and health status (credentials omitted).

---

## 8. Automated Verification & Test Results

The full backend test suite in `JU-TF-26` was executed with pytest:

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\Coding\Hackathons\JU-TF-26
configfile: pytest.ini

tests\test_adaptive_pipeline.py .....................                    [ 16%]
tests\test_generate_validation.py ........                               [ 22%]
tests\test_factual_verification_regression.py ............               [ 32%]
tests\test_preview_and_coding_workflow.py ..........                     [ 39%]
tests\test_source_serializer.py .....                                    [ 43%]
tests\test_wikipedia_summary.py ...............................s         [ 68%]
tests\test_tools_registry.py .........                                   [ 75%]
tests\test_auth_flow.py ....                                             [ 78%]
tests\test_graph_prompt_overrides.py ...                                 [ 81%]
tests\test_graph_schema_api.py ..                                        [ 82%]
tests\test_prompts_composition.py .....                                  [ 86%]
tests\test_prompt_schema_api.py ..                                       [ 88%]
tests\test_workspace_api.py ........                                     [ 94%]
tests\test_workspace_download_api.py .                                   [ 95%]
tests\test_workspace_service.py ......                                   [100%]

======================= 127 passed, 1 skipped in 7.42s ========================
```

### Coverage Highlights:
- **Task Classification:** Low prompts, high-complexity prompts, multimodal file attachments, and ambiguous prompts tested.
- **Candidate Selection:** Lightweight API selection on low tasks, frontier selection on high tasks, multimodal vision matching, explicit user model preferences, and fallback chain construction tested.
- **Fallback Execution:** Primary success, transient failure with fallback recovery, all-fallbacks failure raising `AdaptiveExecutionError`, and secret scrubbing verified.
- **Credential Safety:** Cross-provider credential leakage tests confirmed that Groq keys cannot authenticate OpenAI or Anthropic candidates.
- **API Endpoints:** `/generate`, `/stream`, `/v1/adaptive/classify`, `/v1/adaptive/select`, and `/v1/adaptive/registry` tested.
- **Regression:** All existing validation, factual verification, search tool, and workspace service tests passed with zero regressions.

---

## 9. Known Limitations & Production Guidance

1. **Unit Tests vs Live Provider Reality:** Passing unit tests and mocked fallbacks verify routing architecture and contracts. Live provider responses remain subject to real-world rate limits, network jitter, and provider outages.
2. **Optional Provider SDKs:** Anthropic (`langchain_anthropic`) and Google GenAI (`langchain_google_genai`) are optional dependencies. If not installed in the environment, `build_chat_model` falls back to `ChatOpenAI` endpoints.
3. **Mid-Stream Fallback Constraint:** In streaming execution (`/stream`), fallback occurs before tokens are streamed to the client. Switching models mid-generation after tool side effects have occurred is disabled by design to prevent duplicate tool executions.

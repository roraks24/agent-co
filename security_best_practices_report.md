# Security Best Practices Report

## Executive Summary
This pass implemented env-gated hardening for backend CORS/auth/error handling, moved frontend API key handling to session-first storage with explicit persistence opt-in, and upgraded a vulnerable dependency (`axios`).

High-severity issues identified at the start of the task are fixed in code and validated with tests/build/audit.

## Runtime Assumptions
- `APP_ENV=development` default:
  - `REQUIRE_WORKSPACE_AUTH` defaults to `false`
  - `EXPOSE_VERBOSE_ERRORS` defaults to `true`
  - localhost CORS defaults are enabled
- `APP_ENV=production` default:
  - `REQUIRE_WORKSPACE_AUTH` defaults to `true`
  - `EXPOSE_VERBOSE_ERRORS` defaults to `false`
  - explicit `CORS_ALLOWED_ORIGINS` must be provided

Reference:
- `agent/security_config.py:39`
- `agent/security_config.py:64`
- `agent/security_config.py:68`

## Fixed Findings

### SEC-001 (High) - Wildcard CORS with credentials
- Location:
  - `agent/api.py:735`
  - `agent/api.py:736`
  - `agent/security_config.py:43`
  - `agent/security_config.py:57`
- Impact: wildcard CORS plus credentials can expose authenticated cross-origin request surfaces in browsers.
- Fix: replaced hardcoded permissive CORS with env-driven origin allowlist and credential gating.
- Mitigation: production now requires explicit origin configuration; wildcard with credentials is prevented.
- Status: Fixed.

### SEC-002 (High) - Unauthenticated workspace read/write/delete endpoints
- Location:
  - `agent/api.py:713`
  - `agent/api.py:802`
  - `agent/api.py:814`
  - `agent/api.py:827`
  - `agent/api.py:841`
  - `agent/api.py:1008`
- Impact: unauthenticated clients could access workspace operations in secure deployments.
- Fix: added env-gated workspace auth dependency requiring non-empty `X-API-KEY` when enabled; returns consistent 401 envelope.
- Mitigation: dev ergonomics retained through env defaults; secure mode enforces key presence for all `/workspace/*` routes.
- Status: Fixed.

### SEC-003 (High) - Error detail leakage in workflow responses/stream
- Location:
  - `agent/api.py:1060`
  - `agent/api.py:1063`
  - `agent/api.py:1241`
  - `agent/api.py:1248`
- Impact: raw exception strings/chains in client-visible payloads can leak internals and sensitive context.
- Fix: production-safe error messages now default to non-verbose output; verbose chain/raw details are only emitted when explicitly enabled.
- Mitigation: full exception data remains server-side in logs.
- Status: Fixed.

### SEC-004 (High) - API key persisted by default in `localStorage`
- Location:
  - `frontend/src/app/lib/api-key-storage.ts:52`
  - `frontend/src/app/lib/api-key-storage.ts:78`
  - `frontend/src/app/pages/LiveStudio.tsx:792`
  - `frontend/src/app/pages/LiveStudio.tsx:867`
  - `frontend/src/app/lib/api-client.ts:143`
- Impact: persistent browser storage increases exposure window if client-side compromise occurs.
- Fix: session-first key storage model implemented; optional remember mode persists to local storage only when explicitly chosen.
- Mitigation: startup and run paths use unified key reader; workspace auth failure path is handled with reduced noise and explicit user message.
- Status: Fixed.

### SEC-005 (High) - Vulnerable axios version
- Location:
  - `frontend/package.json:12`
  - `frontend/package-lock.json:1774`
- Impact: known advisories in old `axios` versions.
- Fix: upgraded to patched `axios` release (`^1.13.5`), lockfile regenerated.
- Mitigation: audit shows no current vulnerabilities.
- Status: Fixed.

## Pending Findings

### SEC-006 (Medium) - Workspace "auth" is a key-presence gate, not user identity/authz
- Location:
  - `agent/api.py:713`
- Impact: this is an immediate-risk reduction but does not provide user identity, scoped tokens, or role-based authorization.
- Current Mitigation: env-gated enforcement on workspace routes.
- Recommended Next Step: move to principal-based auth (JWT/session), scope workspace ownership to authenticated subject, and add per-route authorization checks.
- Status: Pending (intentionally out of scope for this pass).

### SEC-007 (Low) - Browser-stored API key remains readable by in-page JavaScript
- Location:
  - `frontend/src/app/lib/api-key-storage.ts:52`
- Impact: any successful XSS in the frontend can still access browser-stored keys.
- Current Mitigation: session-first default and optional persistence toggle.
- Recommended Next Step: move provider calls behind backend-managed credentials or short-lived delegated tokens.
- Status: Pending.

## Validation Evidence
- Frontend tests: `npm run test` (15/15 passed)
- Frontend build: `npm run build` (passed)
- Backend tests: `python -m unittest discover -s tests` (47/47 passed)
- Dependency audit: `npm audit --omit=dev --json` reports 0 vulnerabilities

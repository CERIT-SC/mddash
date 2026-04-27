# Design: Simplify API Response Schema

**Date:** 2026-04-26
**Scope:** `dashboard/api`, `mdrun-api`, `dashboard/ui`, demo harness, tests

## Problem

Both backend APIs wrap every response in an envelope:

- Success: `{success: true, data: ...}`
- Error: `{success: false, message: ...}`

HTTP status codes are set but the caller must also inspect the JSON envelope. A proper REST API uses the status code as the truth-teller and returns the resource directly.

## Goals

1. Remove the `{success, data/message}` envelope from all endpoints.
2. Make HTTP status codes the single source of truth for success/failure.
3. Return raw resources on success, `{detail: "..."}` on error.
4. Update the frontend axios interceptor, hooks, and demo mocks to match.
5. Delete the `ApiResponse` class entirely — routes use Flask conventions directly.

## Success Responses

Return the marshaled resource or primitive directly via `jsonify()`, no wrapper.

| Verb | Example | Status | Body |
|------|---------|--------|------|
| GET | `/experiments` | 200 | `[{id: "abc", ...}]` |
| GET | `/experiments/abc` | 200 | `{id: "abc", ...}` |
| POST | `/experiments` | 201 | `{id: "abc", ...}` |
| DELETE | `/experiments/abc` | 204 | *(empty)* |

Implementation: routes return `jsonify(data)` (default 200), `jsonify(data), 201` for created, `"", 204` for deleted.

## Error Responses

Routes raise `HTTPException` subclasses (`BadRequest`, `NotFound`, `Unauthorized`, etc.). The `@handle_exceptions` decorator catches all exceptions and returns `{detail: "..."}` with the correct HTTP status code.

| Scenario | Status | Body | Route raises |
|----------|--------|------|-------------|
| Not found | 404 | `{detail: "Job xyz not found"}` | `raise NotFound(...)` |
| Bad input | 400 | `{detail: "Invalid engine: foo"}` | `raise BadRequest(...)` |
| Unauthorized | 401 | `{detail: "Not authenticated"}` | `raise Unauthorized(...)` |
| Validation failure | 400 | `{detail: "Missing required field 'name'"}` | `raise BadRequest(...)` |
| Internal error | 500 | `{detail: "..."}` | uncaught exception |

`handle_exceptions` decorator keeps logging behavior (tracebacks for unexpected exceptions, messages only for `HTTPException`).

## Files Changed

### Backend

- `dashboard/api/api_response.py` — **deleted**
- `mdrun-api/api_response.py` — **deleted**
- `dashboard/api/decorators.py` — inlined error formatting logic (was calling `ApiResponse.error()`)
- `mdrun-api/decorators.py` — same, plus `ValidationError` handling
- `dashboard/api/routes/*.py` — replace `ApiResponse.success()` with `jsonify()`, replace `ApiResponse.error()` with `raise HTTPException`; remove `ApiResponse` import
- `mdrun-api/routes.py` — same
- `dashboard/api/tests/unit/test_api_response.py` — **deleted** (class no longer exists)
- `dashboard/api/tests/unit/test_decorators.py` — updated assertions for `{detail}` format
- `dashboard/api/tests/unit/test_mdrepo_routes.py` — updated assertions (no envelope)
- `dashboard/api/_demo/mocks/http.py` — update mock response bodies to raw resources / `{detail}`

### Frontend

- `dashboard/ui/src/lib/http.ts` — remove response interceptor that unwraps `res.data.data`; keep error interceptor, change `message` to `detail`
- All hooks using `api.get(...).then(r => r.data)` continue to work unchanged

## Migration Strategy

Big-bang single PR. Backend and frontend change together because there is no caller other than the bundled frontend. No backward-compatible dual-format period.

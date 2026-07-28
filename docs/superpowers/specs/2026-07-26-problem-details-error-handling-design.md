# Design: Problem-Details Error Handling

**Date:** 2026-07-26 (revised 2026-07-27)
**Scope:** `dashboard/api`, `mdrun-api`, `dashboard/auth`, `dashboard/ui`, demo harness, tests, AGENTS docs

> **Revision 2026-07-27:** `type` now carries a stable `urn:mddash:<token>` (the support-reportable code) instead of `"about:blank"`. The body is a strict superset of v1, so clients reading only `detail` keep working. There is deliberately **no `instance`** field — the `type` token is the single support code, correlated in logs by `type` + time.

## Problem

Error handling across the three Flask services is inconsistent, leaky, and more verbose than it needs to be:

- **Three different error contracts** coexist: `{detail: "..."}` (Dashboard API), `{detail: <string|dict>}` (MDRun API — `detail` is sometimes a marshmallow dict), and bare strings / `{error: "..."}` (Auth service).
- **No `@app.errorhandler` is registered anywhere.** The custom `@handle_exceptions` decorator only catches exceptions raised *inside its own wrapped body*, so routing-level errors (no-match 404, wrong-method 405) and HTTPExceptions raised in undecorated routes (e.g. `dashboard/api/routes/mdrepo.py` OAuth `initiate_auth`) fall through to Werkzeug's default **HTML** error page. Clients receive HTML, not JSON.
- **Internal details leak into client messages.** Unexpected exceptions set `message = str(e)` (`decorators.py:36`, `mdrun-api/decorators.py:40`), surfacing library text, file paths, and K8s error bodies. Authored 5xx messages interpolate raw exceptions (`f"Failed to create notebook pod: {e.reason}"`, `f"Failed to download PDB file: {response.status_code}"`, `f"Invalid compute parameters: {exc}"`).
- **Redaction is ad hoc.** Only `dashboard/api/utils.py:356` (git operations) scrubs secrets before building a message; nothing generalizes the pattern.
- **Rollback is opt-in and easy to forget.** `@handle_exceptions(rollback=True)` requires each mutating route to opt in; a forgotten flag silently leaves a dirty session.
- **Validation is hand-written and divergent.** Dashboard API hand-parses JSON bodies (`request.get_json()` + `isinstance` + `not data` + `BadRequest`), while MDRun API uses marshmallow `ValidationError`. MDRun further hand-checks `np/ntomp > 0` and re-wraps enum `ValueError`s as `ValidationError(str(e))` with `cast()` soup. ~30 routes carry `@handle_exceptions()` decorators that add no behavior beyond what a global handler provides.
- **No React Error Boundary.** Uncaught render-time errors unmount the entire tree with no fallback.

## Goals

1. Adopt a simplified RFC 9457 (Problem Details) shape across all three services, with **no `status` field in the body** (the HTTP status line is the single source of truth, per the prior `2026-04-26` refactor).
2. Use Flask's **native** `@app.errorhandler` mechanism instead of the hand-rolled `@handle_exceptions` decorator, so every error — routed, no-match, wrong-method, undecorated — returns JSON.
3. Never leak stack traces, `str(e)`, file paths, K8s/HTTP response bodies, or secrets to clients. Full detail logged server-side only.
4. Make rollback **automatic** for every uncaught exception.
5. Extend the existing marshmallow `schema.load()` pattern (already used in MDRun API) to **both** APIs and to all request locations — form, query, JSON — eliminating hand-written parsing/typing/validation boilerplate. Move numeric and enum validation/conversion into marshmallow schemas. No new dependency.
6. Keep the UI change minimal: the ~20 `toast.error(error.message)` hooks keep working unchanged.
7. Add a React Error Boundary for render crashes.
8. Replace the `"about:blank"` sentinel with stable **`type` tokens** (`urn:mddash:<token>`) so the UI can branch on known conditions and the token doubles as the single support-reportable error code (correlated in logs by `type` + time).
9. Add an **optional `solution`** member (the user-facing action) only where the cause alone is unhelpful (state / conflict / auth / upstream / 5xx); omit it on validation errors, where `detail` already implies the fix.

## Non-Goals

- No `errors[]` array for validation (flattened to a single `detail` string; can be added later as a non-breaking extension).
- No `instance` / correlation-ID field — the `type` token is the support code; correlation in logs is by `type` + time.
- No custom `type` *scheme* — v1 uses opaque URN tokens (`urn:mddash:<token>`), not a resolvable documentation URL. A later non-breaking upgrade can point `type` at `https://docs.../errors/<token>` once a docs host exists. (RFC 9457 treats `type` as opaque to clients; only `about:blank` has defined semantics, so the URN form is fully conformant.)
- No change to HTTP status codes per route, success-body shapes, or external service contracts (MDRepo/Invenio, MetaDump).
- `validators.py` / `sanitization.py` **stay as functions** — they perform SSRF guards, reserved-IP checks, and regex work that marshmallow fields cannot express. They are not targets for schema migration.

## Error Response Shape

Every error response, from all three services. A value-add error (Problem / Cause / Solution):

```json
{
  "type": "urn:mddash:notebook-quota-exceeded",
  "title": "Resource quota exceeded",
  "detail": "You already have the maximum number of notebooks running.",
  "solution": "Stop another notebook first, then start this one."
}
```

An opaque 5xx (unhandled exception) carries a generic `detail` plus a retry/support `solution`, but no per-occurrence code — the `type` token is the support handle:

```json
{
  "type": "urn:mddash:internal-error",
  "title": "Internal Server Error",
  "detail": "Internal server error. Please try again later.",
  "solution": "Try again in a moment; if the problem persists, contact support."
}
```

A validation error carries **no** `solution` (the `detail` already implies the fix and the UI highlights the field):

```json
{
  "type": "urn:mddash:validation-error",
  "title": "Bad Request",
  "detail": "np: Missing data for required field."
}
```

| Field | Role | When present |
|-------|------|--------------|
| `type` | machine + support handle; RFC 9457 URI reference (URN token). This is the code users report to support. | always — `urn:mddash:<token>`; `about:blank` only as a last-resort default for ad-hoc HTTPExceptions with no mapped token |
| `title` | the **Problem** (stable per type; the HTTP phrase for defaults) | always |
| `detail` | the **Cause** (specific to this occurrence; authored for 4xx, generic for unexpected 5xx) | always |
| `solution` | the **action** the user can take | optional — present where cause alone is unhelpful (state / conflict / auth / upstream / 5xx); omitted on validation errors where `detail` already implies the fix |
| `Content-Type` | `application/problem+json` | always |

**Toast rule (one short line, always):** the UI shows `solution` if present, else `detail`, else `title`. The full structure is available for an expandable error view — never dumped into the toast wholesale.

**Do / Don't:**
- Do emit a real `urn:mddash:<token>` per error category (see catalog below).
- Do map **default** tokens in the global handler (no raise-site churn): `ValidationError` → `validation-error`, routing/`NotFound`/`get_or_404` → `not-found`, `MethodNotAllowed` → `method-not-allowed`, bare `HTTPException` → status-based default, unhandled `Exception` → `internal-error`.
- Do opt in a small set of **value-add** tokens at raise sites the refactor already touches (catalog below). Value-add tokens carry a curated `solution`.
- Do author `solution` only on value-add tokens + `internal-error`.
- Don't add a `solution` field on validation errors (redundant with `detail` + field UI).
- Don't fold `solution` into `detail` (loses structure; defeats separate rendering).
- Don't fold `solution` into `detail` (loses structure; defeats separate rendering).

**Type token catalog (v1):**

Value-add tokens (carrying a `solution`) are raised directly as `ApiError(code, description, type_, solution)`. The remaining defaults are derived from the HTTP phrase (e.g. routing 404 → `not-found`).

| Token | title | When |
|-------|-------|------|
| `urn:mddash:validation-error` | Bad Request | marshmallow `ValidationError` |
| `urn:mddash:not-found` | Not Found | `NotFound` / `get_or_404` / routing 404 (derived) |
| `urn:mddash:method-not-allowed` | Method Not Allowed | routing 405 (derived) |
| `urn:mddash:bad-request` | Bad Request | ad-hoc `BadRequest` (derived) |
| `urn:mddash:conflict` | Conflict | ad-hoc `Conflict` (derived) |
| `urn:mddash:unauthorized` | Unauthorized | ad-hoc `Unauthorized` (derived) |
| `urn:mddash:forbidden` | Forbidden | ad-hoc `Forbidden` (derived) |
| `urn:mddash:internal-server-error` | Internal Server Error | authored `InternalServerError` (derived) |
| `urn:mddash:notebook-quota-exceeded` | Resource quota exceeded | notebook max reached |
| `urn:mddash:notebook-already-exists` | Conflict | notebook pod already exists |
| `urn:mddash:gpu-unavailable` | GPU not available | GPU requested but unconfigured |
| `urn:mddash:auth-required` | Unauthorized | session missing/expired (auth service) |
| `urn:mddash:auth-forbidden` | Forbidden | user mismatch (auth service) |
| `urn:mddash:upstream-download-failed` | Bad Gateway | PDB / repo / MDPosit download failure |
| `urn:mddash:upstream-unavailable` | Bad Gateway | MDRepo / Invenio / MetaDump upstream 5xx |
| `urn:mddash:simulation-locked` | Conflict | manifest is read-only / locked |
| `urn:mddash:mdrepo-not-configured` | Internal Server Error | MDRepo env incomplete |
| `urn:mddash:mdposit-not-configured` | Internal Server Error | `MDPOSIT_URL` unset |
| `urn:mddash:internal-error` | Internal Server Error | unhandled `Exception` |

The HTTP status code lives **only** on the response status line. The `type` URN uses an **informal** namespace (`mddash` is not IANA-registered) — acceptable for an internal app and widely done; it upgrades to a resolvable `https://docs.../errors/<token>` later as a non-breaking change.

## Architecture

### 1. Native Flask error handlers replace the decorator

Delete `@handle_exceptions` entirely. The only behavior it provided beyond shaping was `db.session.rollback()` — that moves into the global `Exception` handler, making rollback **automatic for every uncaught exception**.

Each service gets a small `errors.py` with one `ApiError` exception + `register_error_handlers(app)`. `ApiError` carries `code`/`description`/`problem_type`/`problem_solution` and renders itself via `to_response()` — there is no separate `problem()` builder. Both APIs handle marshmallow `ValidationError` identically (previously only MDRun did), which unifies the validation conventions:

```python
# dashboard/api/errors.py  (mdrun-api/errors.py is identical; auth/errors.py drops db.rollback + ValidationError handler)
class ApiError(HTTPException):
    problem_type: str
    problem_solution: str | None

    def __init__(self, code: int, description: str, type_: str, solution: str | None = None) -> None:
        super().__init__(description=description)
        self.code = code
        self.problem_type = type_
        self.problem_solution = solution

    def to_response(self) -> Response:
        body = {"type": self.problem_type,
                "title": HTTPStatus(self.code).phrase,
                "detail": self.description or "An error occurred."}
        if self.problem_solution is not None:
            body["solution"] = self.problem_solution
        resp = jsonify(body)
        resp.mimetype = "application/problem+json"
        resp.status_code = self.code
        return resp

def flatten_messages(messages) -> str:
    # marshmallow ValidationError.messages (str|dict|list) -> one readable line
    ...

def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def _validation(exc: ValidationError) -> Response:
        detail = flatten_messages(exc.messages)          # no `solution` — detail already implies the fix
        return ApiError(400, detail, "urn:mddash:validation-error").to_response()

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException) -> Response:
        if not isinstance(exc, ApiError):
            # ad-hoc HTTPExceptions derive their type from the HTTP phrase: "Not Found" -> urn:mddash:not-found
            name = exc.name or "Internal Server Error"
            exc = ApiError(exc.code or 500, exc.description or "An error occurred.",
                           f"urn:mddash:{name.lower().replace(' ', '-')}")
        code = exc.code or 500
        logger.log(logging.WARNING if code < 500 else logging.ERROR,
                   "%s %s -> %s [%s]: %s", request.method, request.path, code, exc.problem_type, exc.description,
                   exc_info=code >= 500)
        return exc.to_response()

    @app.errorhandler(Exception)
    def _unhandled(_exc: Exception) -> Response:
        db.session.rollback()
        logger.error("Unhandled exception on %s %s", request.method, request.path, exc_info=True)
        return ApiError(500, "Internal server error. Please try again later.",
                        "urn:mddash:internal-error",
                        "Try again in a moment; if the problem persists, contact support.").to_response()
```

Value-add errors are raised directly as `ApiError`; the exception carries its token + solution and renders itself:

```python
raise ApiError(HTTPStatus.CONFLICT, "Notebook pod already exists.",
               "urn:mddash:notebook-already-exists",
               "The notebook is already running; open it instead.")
```


Flask routes `HTTPException` (and subclasses: `NotFound`, `BadRequest`, `ServiceUnavailable`, `get_or_404`, `abort`) to `_http`, marshmallow `ValidationError` to `_validation`, and everything else to `_unhandled`. Routing 404/405 and undecorated-route raises are now caught — no more HTML leaks. The auth service registers the same handlers but without the `db.session.rollback()` line and without the `ValidationError` handler (no marshmallow / no DB).

### 2. Plain marshmallow `schema.load()` for request parsing

No new dependency. marshmallow is already present (flask-marshmallow + marshmallow-sqlalchemy) and MDRun API already uses the target pattern at `routes.py:103`: `data = cast("dict[str, Any]", request_schema.load(request.json or {}))`. The refactor extends that one pattern to **both** APIs and to form/query locations, so all request parsing/validation converges on `schema.load()` → `ValidationError` → global `_validation` handler → problem details.

Routes keep their existing `request.get_json()` / `request.form` / `request.args.get(...)` extraction line (one line), then hand the dict to a schema. The schema does all validation and conversion; the route receives validated, already-converted values. This is uniform — including the multipart experiments POST (form fields via `schema.load(request.form)`, files stay `request.files.getlist(...)`), so there is no "partial-adoption" inconsistency.

**Representative before/after** — `notebook.py` `start_notebook`:

```python
# BEFORE: manual parsing, type checks, enum try/except
body = request.get_json(silent=True) or {}
tier_str = body.get("tier")
gpu_value = body.get("gpu", False)
if "gpu" in body and not isinstance(gpu_value, bool):
    raise BadRequest(description="Field 'gpu' must be a JSON boolean.")
gpu = gpu_value
try:
    tier = NotebookTier(tier_str) if tier_str else None
except ValueError:
    valid = ", ".join(t.value for t in NotebookTier)
    raise BadRequest(description=f"Unknown notebook tier '{tier_str}'. Valid tiers: {valid}")
notebook.start(tier=tier, gpu=gpu)

# AFTER: schema does it all
data = StartNotebookSchema().load(request.get_json(silent=True) or {})
notebook.start(tier=data["tier"], gpu=data["gpu"])
```

**The schema** carries validation + enum conversion, preserving case-insensitivity (per the AGENTS note on `from_string`):

```python
class StartNotebookSchema(Schema):
    tier = fields.Str(load_default=None)   # validated below; None means "default tier"
    gpu = fields.Bool(load_default=False)

    @validates("tier")
    def _check_tier(self, value):
        if value is not None:
            NotebookTier.from_string(value)   # raises ValueError -> ValidationError

    @post_load
    def _to_enum(self, data, **kwargs):
        if data.get("tier") is not None:
            data["tier"] = NotebookTier.from_string(data["tier"])
        return data
```

**MDRun schemas** get the same treatment: `np`/`ntomp` become `fields.Int(required=True, validate=Range(gt=0))` (deleting the manual `if np <= 0` checks and `int(data["np"])` casts), and `pme`/`nb`/`binary`/`ewald` use `@validates` + `@post_load` for case-insensitive enum conversion (deleting the `try: ... from_string ... except ValueError as e: raise ValidationError(str(e)) from e` re-wraps). Routes receive already-validated, already-converted values — no `cast()` soup. The existing `cast("dict[str, Any]", request_schema.load(...))` becomes plain `request_schema.load(...)` since the schema now returns converted types.

**Why not webargs or flask-pydantic:** webargs only saves the one `request.get_json()` extraction line (kwarg injection is its real extra), at the cost of a new dependency, a `parser.error_handler` override (422→400), and non-uniform application (multipart breaks `@use_kwargs`). flask-pydantic introduces pydantic as a second validation system alongside the existing marshmallow. Plain `schema.load()` gets the full validation boilerplate win with no new dependency and uniform application.

### 3. Redaction rule (the leak fix)

- **4xx HTTPException:** `detail = exc.description` — the authored message. **Must not interpolate raw exception objects** (`str(e)`, `e.reason`, `response.status_code`, `data`, library text). Audit and rewrite the offending 4xx sites (e.g. `gmx.py:77`, `amber.py:77`, `analysis.py:263`).
- **5xx HTTPException (authored):** `detail = exc.description` — authored, clean. The offending 5xx sites that today interpolate internals (`gromacs_job.py:293`, `notebook.py:154`, `experiment.py:255,726`, `experiment_sources.py:143,184`, `metadump.py:39`) are rewritten to author a clean message and rely on `from e` + the handler's `exc_info=True` (5xx) to log internals server-side. Example:
  ```python
  except k8s.ApiException as e:
      raise InternalServerError("Failed to create notebook pod.") from e   # internals logged via __cause__ chain
  ```
- **Unexpected Exception (non-HTTP):** generic `detail`. `str(e)` is never sent to the client.
- Generalize the existing git-secret redaction (`utils.py:356`) into a small `_redact()` helper used wherever a message must include a caller-supplied string (URLs, identifiers) — never exception/secret text.

### 4. Redundant model-layer logging removal

With the global handler now logging all 5xx tracebacks, **log-then-raise** sites in models double-log. Audit and remove the `logger.exception(...)` call where it immediately precedes a `raise` (the handler logs the traceback via `exc_info=True` and the authored `detail` carries the message). Example: `notebook.py:153` logs then `raise InternalServerError` — drop the model log.

**Swallow-and-continue sites stay** — they are the only log of an eaten exception (the exception never reaches a route). These include: `gromacs_job.py:335,363,...` (return `None`), `experiment.py:455` (best-effort MDRepo status, rolled back), `experiment.py:480,487,494` (best-effort cleanup in `delete()`), `notebook.py:186,191` (best-effort `stop()`), `tuner_job.py:119,121,197,221`, `simulation_job.py:91`, `analysis_job.py:277`.

### 5. Frontend: `ApiError` class + Error Boundary

`dashboard/ui/src/lib/http.ts` interceptor builds an `ApiError` exposing `{type, title, detail, solution, status}`. `error.message` is set to the **toast line** (`solution ?? detail ?? title`), so all existing `toast.error(error.message)` call sites and the `QueryCache.onError` (`query-client.ts:9`) keep working unchanged while now showing the actionable line when a `solution` is present:

```ts
export interface ProblemDetails {
  type: string
  title: string
  detail: string
  solution?: string
}

export class ApiError extends Error {
  constructor(
    public type: string,
    public title: string,
    public status: number,
    detail: string,
    public solution?: string,
  ) {
    super(solution ?? detail ?? "Request failed.")   // toast line: solution → detail → title fallback
    this.name = "ApiError"
  }
}

function problemInterceptor(error: unknown) {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 0
    const data = error.response?.data
    const p = data && typeof data === "object" ? (data as Partial<ProblemDetails>) : {}
    return Promise.reject(new ApiError(
      p.type ?? "urn:mddash:internal-error", p.title ?? "", status,
      p.detail ?? "Request failed.", p.solution,
    ))
  }
  return Promise.reject(error instanceof Error ? error : new Error("Request failed."))
}

api.interceptors.response.use((res) => res, problemInterceptor)
apiRaw.interceptors.response.use((res) => res, problemInterceptor)
```

A small `errorSolutions` map (token → copy) may be added later for fully client-owned solutions, but v1 sources `solution` from the backend response field directly — keeping authoring next to the domain logic that knows the cause.

`apiRaw` (byte downloads) gains the same interceptor so `send_file` error responses also surface as `ApiError` instead of raw axios errors.

New `dashboard/ui/src/components/ErrorBoundary.tsx` wraps the app root, catches render-time errors (not API errors), and renders a fallback with a "Reload" button. Wired in `src/router.tsx` (or `App.tsx`).

## Simplifications Summary

What the new mechanism eliminates:

| Before | After |
|--------|-------|
| `@handle_exceptions()` on ~30 routes (+ `rollback=True` flags) | deleted; global handler does it all, rollback automatic |
| `dashboard/api/decorators.py` + `mdrun-api/decorators.py` (duplicated) | deleted |
| Manual `request.get_json()`/`isinstance`/`not data`/`BadRequest` in Dashboard API JSON routes | `schema.load(request.get_json(silent=True) or {})` |
| Manual `request.form[...]` / `request.args.get(...)` parsing | `schema.load(request.form)` / `schema.load(request.args)` |
| MDRun `int(data["np"])` + `if np <= 0: raise ValidationError` + `cast()` soup | `fields.Int(validate=Range(gt=0))` in schema |
| MDRun `try: DeviceType.from_string(...) except ValueError as e: raise ValidationError(str(e)) from e` | `@validates` + `@post_load` in schema; route receives enum |
| Dashboard `NotebookTier(tier_str)` try/except + `isinstance(gpu, bool)` check | schema `@validates` + `fields.Bool` |
| Log-then-raise `logger.exception` in models (~3-5 sites) | removed; global handler logs 5xx traceback |
| Routing 404/405 + undecorated raises → HTML | JSON problem details |
| Three error contracts (`{detail}` str, `{detail}` dict, bare strings) | one `{type,title,detail[,solution]}` everywhere |
| `about:blank` for every error (no machine handle, no support code) | `urn:mddash:<token>` per category — the support-reportable code |
| `str(e)` leak on unexpected 5xx | generic detail + retry/support `solution`; traceback server-side only |
| Dashboard validation = `BadRequest`, MDRun validation = `ValidationError` (divergent) | both = `ValidationError` → same handler → same shape |

## Files Changed

### Backend — new files
- `dashboard/api/errors.py` — `ApiError` exception (carries token + optional solution, renders itself via `to_response()`), `flatten_messages()`, `register_error_handlers(app)` (with `ValidationError` + `HTTPException` + `Exception` handlers). Default `type` is derived from the HTTP phrase (no lookup table); the `type` token is the support-reportable code (no `instance`).
- `mdrun-api/errors.py` — identical.
- `dashboard/auth/errors.py` — same handlers minus `db.session.rollback()` and minus the `ValidationError` handler (no marshmallow / no DB).

### Backend — deleted
- `dashboard/api/decorators.py`
- `mdrun-api/decorators.py`
- `dashboard/api/tests/unit/test_decorators.py`

### Backend — wiring
- `dashboard/api/app.py` (`create_app`) — call `register_error_handlers(app)`.
- `mdrun-api/app.py` (`create_app`) — call `register_error_handlers(app)`.
- `dashboard/auth/auth.py` — adopt `register_error_handlers(app)`; replace bare-string tuples (`auth.py:191,193,199,202,208`) and `{"error": ...}` (`:232`) with `raise BadRequest("...")` / `raise Unauthorized("...")` etc. — the global handler shapes them.

### Backend — dependency
- No new dependencies. marshmallow is already present in both APIs (flask-marshmallow + marshmallow-sqlalchemy).

### Backend — routes: remove decorator + adopt schema.load()
- `dashboard/api/routes/*.py` (`analysis.py`, `amber.py`, `experiments.py`, `files.py`, `gmx.py`, `misc.py`, `notebook.py`, `simulations.py`, `tuner.py`, decorated `mdrepo.py` routes) — remove `@handle_exceptions(...)` lines + imports; replace manual parsing with `schema.load(request.<location>)` where applicable. Remove now-unused `from http import HTTPStatus` where only error codes were used (keep where `CREATED`/`NO_CONTENT`/`ACCEPTED` success codes remain).
- `mdrun-api/routes.py` — remove `@handle_exceptions` from all routes; remove import; replace manual body parsing with `schema.load(request.get_json(silent=True) or {})`; drop `cast()` soup now that schemas return converted types.

### Backend — schemas: absorb validation/conversion
- `mdrun-api/schemas.py` — `np`/`ntomp` → `fields.Int(required=True, validate=Range(gt=0))`; `pme`/`nb`/`binary`/`ewald` → `@validates` (case-insensitive via `from_string`) + `@post_load` enum conversion.
- `dashboard/api/schemas/` — add input schemas for JSON/form/query routes that currently hand-parse (e.g. `StartNotebookSchema`, `PublishSchema`, `SubmitAnalysisSchema`, list-results query schema). Existing output schemas unchanged.

### Backend — redaction + value-add tokens (clean authored messages, no internal interpolation)
- `dashboard/api/routes/gmx.py:77`, `amber.py:77` — `BadRequest(f"Invalid compute parameters: {exc}")` → clean message; log `exc` server-side.
- `dashboard/api/routes/analysis.py:263` — `UnprocessableEntity(f"Failed to read analysis result: {e}")` → clean message + `from e`.
- `dashboard/api/models/gromacs_job.py:293`, `notebook.py:153-154`, `experiment.py:255,726`, `experiment_sources.py:143,184`, `clients/metadump.py:39` — strip `f"...{internal}"`; keep clean `description`; rely on `from e` for server-side traceback. Remove the redundant `logger.exception` at `notebook.py:153` (log-then-raise; handler now logs).
- `dashboard/api/utils.py:356` — keep redaction; extract `_redact()` into a reusable helper if other sites need it.
- Value-add tokens + `solution`: attach `exc.problem_type` / `exc.problem_solution` at the raise sites listed in the token catalog (notebook quota, notebook-already-exists, GPU, simulation-locked, mdrepo/mdposit-not-configured, upstream-download-failed, upstream-unavailable, auth-required, auth-forbidden). Default tokens are derived from status in the handler, so sites without a value-add token need no change.

### Backend — tests
- `dashboard/api/tests/unit/test_errors.py` — **new**: no-route 404 returns JSON problem (not HTML); wrong-method 405 returns JSON; `BadRequest` returns `{type,title,detail}`; `ValidationError` returns flattened `detail` + 400 + `type=urn:mddash:validation-error`; unhandled exception returns generic detail (assert `!= str(e)`) + status 500 + `type=urn:mddash:internal-error` + a retry/support `solution` (no `instance`); a value-add-token HTTPException returns its `type` + `solution`; 5xx HTTPException logs traceback; `schema.load()` parse failure → problem details.
- `mdrun-api/tests/test_errors.py` — **new**: same + `ValidationError` flattening (`{"np": ["Missing data..."]}` → `detail` string) + `schema.load()` validation path.
- `dashboard/api/tests/unit/test_mdposit_publish.py:124` — `"MDRepo" in resp.get_json()["detail"]` still passes (detail preserved); verify.
- `mdrun-api/tests/test_routes.py:127` — `"detail" in data` still passes; verify. Update body assertions that assumed dict-`detail` to the flattened string.
- `dashboard/api/tests/conftest.py`, `mdrun-api/tests/conftest.py` — apply `register_error_handlers` in the test app factory (mirrors production `create_app`).
- `dashboard/auth/tests/test_auth.py` — update body assertions for new problem shape (most are status-only; verify bare-string assertions).
- Route tests using the Flask test client continue to pass (request parsing moves into `schema.load()` but HTTP behavior is preserved).

### Frontend
- `dashboard/ui/src/lib/http.ts` — replace interceptor with `ApiError` builder exposing `{type,title,detail,solution,status}`; `error.message = solution ?? detail ?? title` (toast line); add same interceptor to `apiRaw`. Update header comment.
- `dashboard/ui/src/components/ErrorBoundary.tsx` — **new**: class component `componentDidCatch` + fallback UI with reload.
- `dashboard/ui/src/router.tsx` (or `App.tsx`) — wrap root with `<ErrorBoundary>`.
- A small "Report issue" affordance (optional, v1.1) can surface `type` for support (e.g. a copy button on the `type` token); the toast itself shows only the one-line `solution ?? detail`. No changes required to `hooks/use-*.ts` or `lib/query-client.ts` — they consume `error.message` unchanged.

### Demo harness
- `dashboard/api/_demo/mocks/http.py` — update internal-service (MDRun API) mock error bodies from `{"detail": "..."}` to `{"type":"urn:mddash:<token>","title":"...","detail":"..."}` (~7 sites: `:167,173,189,195,823,831,859`); use the matching token (`not-found` for the job/project-not-found mocks). External-service mocks (MDRepo/Invenio `{"message":...}`) unchanged.

### Docs
- `AGENTS.md` (root) — update "Error Handling" section: replace `@handle_exceptions`/`{detail}` with problem-details shape + native handlers + automatic rollback + marshmallow `schema.load()` for parsing.
- `dashboard/api/AGENTS.md` — update "Core Practices": remove `@handle_exceptions`/`rollback=True` instruction; state routes raise `HTTPException`, use `schema.load()` for parsing, app handlers convert to problem details, rollback is automatic.
- `mdrun-api/AGENTS.md`, `dashboard/ui/AGENTS.md` — update error contract references (`{detail}` → problem details; `ApiError`).

## Migration Strategy

Big-bang single PR. Backend, frontend, demo harness, and tests change together — the only API caller is the bundled frontend, so no backward-compatible dual-format period is needed (established precedent in `2026-04-26-simplify-api-response-design.md`). No HTTP status codes change, so integration tests asserting only on status codes remain green. No new dependency is introduced.

## Verification

After implementation, all of the following must pass:

```bash
make fix            # format + auto-fix Python and frontend
make type-check     # ty (Python) + tsc (TypeScript)
make test           # Python unit/integration tests
```

Plus manual: hit a no-match URL (`/dash/api/does-not-exist`) and confirm a JSON problem-details response with `type=urn:mddash:not-found` (not HTML); trigger an unhandled exception and confirm the client sees only the generic `detail` plus a retry/support `solution` (no per-occurrence code), while the server log shows the full traceback; POST a malformed body to a `schema.load()` route and confirm a 400 problem-details response with `type=urn:mddash:validation-error` and a flattened validation `detail` (no `solution`); trigger a value-add error (e.g. notebook quota) and confirm `type` + `solution` are present and the toast shows the `solution`.

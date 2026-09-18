# Experiment Archivation - Design

- **Issue:** [CERIT-SC/mddash#119](https://github.com/CERIT-SC/mddash/issues/119): *"Completed experiments can be archived so they no longer take up space on the local PVC and only live in the S3."*
- **Status:** Approved (design review 2026-09-17)
- **Scope:** Experiment-level archive **and** restore. Per-simulation archives, partial restore, auto-archive policies, and S3 browsing UIs are out of scope.

## Summary

Archiving must not fight the `rclone bisync` loop: local deletions propagate to S3 (`--force`), so naive "copy to S3, delete locally" would destroy the S3 copy. Furthermore, an empirical check with the pinned `rclone/rclone:1.74.4` against the production `rclone-filters.txt` shows that **all experiment data, including heavy simulation outputs (.xtc, .edr, .tpr, .gro, .log), is already synced to S3 continuously** (the `- **/*.xtc/**` lines only match *contents of directories* ending in those extensions, not files). Re-uploading everything into a tarball would be pure waste.

The design therefore:

1. Adds one static filter line, `- /_archives/**`, so bisync ignores that bucket prefix in both directions.
2. Archives by **S3 server-side copy** of the already-synced live prefix into `_archives/{id}/`, plus a **filtered delta top-up** from the PVC for anything not yet synced: archive completes in seconds regardless of experiment size, with no full re-upload and no compression CPU.
3. Verifies the archive (`rclone check --size-only`) before deleting the local directory.
4. Lets bisync's normal delete-propagation clean the live S3 prefix on its own, with zero changes to the sync loop.
5. Executes archive/restore/purge as **durable Kubernetes Jobs** (the proven MDRepo-upload pattern), driven by a thin worker image built from the already-pinned `rclone/rclone:1.74.4`.

## Background facts

| Fact | Consequence |
|---|---|
| Bisync runs with `--force`; user-initiated local deletes propagate to S3. | Archive data must live outside the synced namespace: the filter-excluded prefix `_archives/`. |
| All experiment files (incl. heavy binaries) are already on S3 within ~one sync cycle (the `**/*.xtc/**` patterns intentionally exclude GROMACS temp *directories*, not files, per `682c12b7`). | Archive ≈ server-side copy + small delta; no tarball re-upload. |
| Bisync syncs the whole bucket ↔ `/mddash`. | Any unfiltered S3 prefix would be downloaded to the PVC, hence the mandatory filter line. |
| MDRepo upload already implements: status doc on PVC + deterministic Job + worker image + API reconciliation. | Archive/restore/purge mirror that pattern (`archive/` package mirrors `upload/`). |
| The API container already receives `S3_BUCKET`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` via `_API_PASSTHROUGH_ENV`. | No new credential plumbing. |
| DB changes require an Alembic migration; fresh DBs are created by the same migrations. | One new migration file in `dashboard/api/migrations/versions/`. |
| The UI already has a disabled **Archive** menu item and a disabled **Archived** tab with TODOs. | UI work is enabling + extending stubs, not new structure. |
| The card menu's **Duplicate** is disabled (no API endpoint). | Stays disabled on both tabs; duplication is out of scope. |

## Lifecycle & state semantics

### Archive flow

1. **Gate checks (API, submit time):** no live tuner/simulation/analysis jobs (`JobStatus.is_live`), no active MDRepo upload (`_read_upload_state` in `UploadState.active()`), not already archived/archiving/restoring, S3 configured (`S3_BUCKET` non-empty). A **running notebook is auto-stopped** (`notebook.stop()`, same precedent as `Experiment.delete()`); the confirm dialog discloses this.
2. API snapshots card state into DB columns (`archived_size_bytes`, `archived_step`, `archived_status`) and submits the archive Job. `archive_state` reports `archiving` (durable UI state).
3. Worker mirrors the experiment dir to `s3://{bucket}/_archives/{id}/` (server-side copy → filtered delta top-up → `rclone check`), writes status `completed`, then deletes the local dir. Bisync propagates the live-prefix deletion.
4. The API infers completion via reconciliation (see below) and sets `archived_at`; the experiment moves to the Archived tab. On failure: `archive_failed` durable alert on the card (reason from status doc), experiment stays Active, retry is idempotent.

**Why reconciliation, not a doc read:** the archive status doc lives inside the experiment dir and is deleted along with it, and K8s Jobs TTL-expire after 5 minutes; neither is durable. The durable markers are the DB itself: non-NULL snapshot columns set at submit time mark "archive submitted"; missing local dir after that means the worker passed its check and deleted the dir (only the worker deletes it as part of this flow). So `archived_at` is set when: snapshots non-NULL **and** `/mddash/{id}` is missing **and** the archive Job is not live. Reconciliation runs in the experiment schema's `pre_dump` (before field extraction), and the `archive_state` property consumes that stashed answer instead of re-reconciling mid-dump, so `archived_at` and `archive_state` never disagree within a single payload. A user manually `rm -rf`-ing the experiment dir from Jupyter mid-archive can produce the same signal with a possibly-partial archive; accepted risk for this iteration (Restore's non-empty check catching a completely empty prefix, and the archive confirm dialog warning users not to touch files during archiving, bound it).

**Job liveness:** a Job is live until it carries a terminal `Complete`/`Failed` condition, never by `status.active > 0` alone. A freshly created Job spends its first seconds Pending (scheduling, image pull); counting that window as dead would flash `*_failed` on submission and, because `archived`/`archiving` in-flight states drive the UI polling, would stop the poll that reports progress.

### Archived state

- Frozen row: `step`/`status`/`size_bytes` serialize from the snapshot columns (`_step_status()` early-returns the snapshot when `archived_at` is set; manifests are gone). File-derived job properties likewise serve persisted columns only, so list serialization of archived experiments does not spawn `NotFound` warnings from manifest lookups.
- Allowed actions: **Rename** (existing PATCH), **Duplicate** (remains disabled), **Restore**, **Delete**.
- Card navigation into the wizard is disabled; a deep-link to an archived experiment renders an archived notice with a Restore action.
- **Delete** removes the DB row and submits a best-effort purge Job for `s3://{bucket}/_archives/{id}/` (no local dir exists). Purge failure is logged only; residual objects are a cost issue, not a correctness issue.

### Restore flow

1. **Gate checks:** experiment is archived, no job in flight, S3 configured, and the local experiment dir either **does not exist** or contains a non-completed restore status doc (the retry sentinel; a failed or evicted restore always leaves its doc behind, so its own leftover must be re-submittable). Any other dir contents → 409, protecting against clobbering foreign files. The worker enforces the same gate: a present dir continues only when it holds a non-completed restore doc, and `rclone copy` resumes into the partial data left by the interrupted attempt.
2. Job: verify `_archives/{id}` non-empty → `rclone copy` back to `/mddash/{id}` → `rclone check --size-only` → status `completed`. This is the one inherently slow direction (real download); it is why durable Jobs are used for all operations uniformly.
3. On success `archived_at` is cleared; card returns to Active; `step`/`status` recompute from real files on next poll. Bisync re-syncs the restored files to the live prefix naturally.

### State model

`archive_state` (derived, serialized): `null | archiving | archived | restoring | archive_failed | restore_failed`

- `null`: normal active experiment (`archived_at IS NULL`, snapshot columns NULL).
- `archiving`: snapshots set, `archived_at` NULL, archive Job live.
- `archived`: `archived_at IS NOT NULL`, no restore doc, and no live restore Job.
- `restoring`: `archived_at IS NOT NULL` and the restore Job is live. A live Job outranks even a stale `failed` sentinel from the attempt it replaces, so a retry flips to `restoring` (and clears the failure banner) immediately.
- `archive_failed`: snapshots set, `archived_at` NULL, local dir still present, and (doc terminal `failed`, doc active without live Job, or no doc and no live Job; the `job_missing` analogue from `_read_upload_state`. An evicted pod leaves an unretried dead Job, `backoffLimit: 0`, so a doc alone must never pin the state).
- `restore_failed`: `archived_at IS NOT NULL` and a restore doc exists (terminal `failed`, or active without a live Job) with no live restore Job.

Reconciliation runs in the read paths (list/detail/status), same as upload; the only DB mutations are: snapshots at archive-submit, `archived_at` set/cleared by reconciliation, and snapshots cleared when `archived_at` is cleared.

**DELETE while an archive/restore Job is in flight:** the API foreground-deletes any `archive-{id}` / `restore-{id}` Job first (same helper style as `delete_upload_resources`), then proceeds with the normal delete plus the purge Job.

## Storage layout & sync integration

- Prefix: `s3remote:{S3_BUCKET}/_archives/{experiment_id}/…`, a plain file tree (no tarball), byte-for-byte mirror of the sync-worthy experiment content.
- The two filter files have distinct consumers and get distinct additions:
  - `dashboard/s3-sync/rclone-filters.txt` (baked into the s3-sync image, consumed by the bisync loop): add `- /_archives/**`. Mandatory; without it bisync downloads every archive back onto the PVC and resurrects purged prefixes from that local copy. The s3-sync Dockerfile must copy this file explicitly (`s3-sync/rclone-filters.txt`), because the build context is `dashboard/` and a bare `rclone-filters.txt` resolves to the mdrepo-uploader list.
  - `dashboard/rclone-filters.txt` (baked into the mdrepo-uploader image, defines what is upload-worthy to MDRepo): add `- **/.archive-status.json` and `- **/.archive-status.json.tmp`, mirroring its existing `.mdrepo-upload.json` entries. `_archives/` needs no entry here: it lives outside every experiment dir, and uploads are per-experiment.
- The sidecar startup also deletes any stray `/mddash/_archives` tree before the loop starts: the prefix is excluded now, so bisync would never remove a previously-downloaded copy itself. (bisync-downloaded dirs arrive owner-read-only; the cleanup restores the write bit first.)
- The filter change to the s3-sync copy triggers the existing filters-change recovery resync once per user pod at rollout (`setup_rclone` in `sync.sh`), the same sanctioned path used by previous filter edits; no new sync-loop code.
- Archive-worthiness is defined exactly once: the archive-worker image bakes in `dashboard/s3-sync/rclone-filters.txt` (the bisync definition) and the delta top-up runs `rclone copy --filter-from /rclone-filters.txt` with it. The archive therefore contains precisely what bisync would sync (excludes `.binder-env` conda trees, checkpoints, `mwf_*` intermediates, `.storage_size`, etc.).

## Execution: durable Jobs + worker

New API package `dashboard/api/archive/` mirroring `dashboard/api/upload/`:

- `status.py`: status doc at `DATA_DIR/{id}/.archive-status.json`, attempt-fenced atomic writes (same shape as upload's): `{attempt_id, state, direction ∈ {archive, restore}, reason?}`. The doc lives inside the experiment dir; archive's final `completed` is written *before* the local `rm -rf`, and DB-flag reconciliation makes the terminal state durable after the doc is gone. **Restore never gets an API-side queued doc**: writing it would recreate the very directory the worker checks for and copies into; restore in-flight is reconstructed from the live Job, and the worker writes the doc (which its `write_status` creates the parent dir for).
- `submission.py`: deterministic Job names `archive-{id}` / `restore-{id}` / `purge-{id}` (same `_dns1123_name` hashing), labels `mddash.io/experiment={id}` + `mddash.io/preserve-on-stop=true` (so the culler preserves them), non-root security context (UID 1000, drop all caps), `backoffLimit: 0`, `activeDeadlineSeconds: 86400`, `ttlSecondsAfterFinished: 300`, PVC mounted at `/mddash`, S3 env from the API's own environment. A retry foreground-deletes the previous terminal Job and **waits for it to disappear** before creating the new one (the API server rejects creates with "object is being deleted" while the old object terminates); a failed submission removes only archive's own queued doc (the restore sentinel must survive) and surfaces to the client as a 409 with a retry-later solution, never a generic 500.

New worker image `dashboard/archive-worker/`:

- `Dockerfile`: `FROM rclone/rclone:1.74.4` + `COPY worker.sh /worker.sh` (POSIX sh; entrypoint runs `sh /worker.sh <archive|restore|purge> --experiment-id … --attempt-id …`).
- `archive` mode:
  1. `rclone copy s3remote:{bucket}/{id} s3remote:{bucket}/_archives/{id}` (server-side; no egress).
  2. `rclone copy --filter-from /rclone-filters.txt /mddash/{id} s3remote:{bucket}/_archives/{id}` (delta only).
  3. `rclone check s3remote:{bucket}/_archives/{id} /mddash/{id} --filter-from /rclone-filters.txt --size-only` (size-only because multipart S3 ETags are not MD5s).
  4. Write status `completed`, then `rm -rf /mddash/{id}`.
- `restore` mode: fail if `_archives/{id}` empty or a leftover dir holds anything but a non-completed restore doc (continuation of the interrupted attempt) → `rclone copy s3remote:{bucket}/_archives/{id} /mddash/{id}` → `rclone check --size-only` → status `completed`.
- `purge` mode: `rclone purge s3remote:{bucket}/_archives/{id}` (best-effort).
- Status writes via printf JSON; failures write `failed` with a short sanitized `reason` (no secrets, fixed tokens).

## API & schema deltas

- `POST /api/experiments/{id}/archive` → `202 {attempt_id}`. Errors: 404 unknown; 409 `urn:mddash:archive-conflict` (live jobs / active upload / already archived or in flight / local precondition failure); 409 `urn:mddash:archive-submission-failed` (Job submission failed; retry later); 400 `urn:mddash:s3-not-configured`.
- `POST /api/experiments/{id}/restore` → `202`. Errors: 409 `urn:mddash:archive-conflict` (not archived / in flight / local dir exists); 409 `urn:mddash:archive-submission-failed`; 400 `urn:mddash:s3-not-configured`.
- `GET /api/experiments/{id}/archive/status` → `{archive_state, direction, attempt_id, reason?}` (status doc reconciled with live Job, mirrors `get_publish_status`).
- `DELETE /api/experiments/{id}`: unchanged contract; archived experiments additionally submit the purge Job; the local-dir `rmtree` thread no-ops on a missing dir.
- DB migration: nullable `archived_at` (DateTime), `archived_size_bytes` (Integer), `archived_step` (Integer), `archived_status` (String(32)) on `experiments`. Plain types (no `db.Enum`) to avoid name/value hazards per `dashboard/api/AGENTS.md`.
- `ExperimentSchema` gains `archived_at` and derived `archive_state`; `size_bytes` returns `archived_size_bytes` while archived; `step`/`status` return the snapshots while archived.
- `dashboard/api/openapi.yaml` updated; `pnpm api:generate` regenerates the UI client (drift fails CI).
- Helm/config: `ARCHIVE_WORKER_IMAGE` added to `values.yaml.tmpl` and `_API_PASSTHROUGH_ENV` (mirrors `MDREPO_UPLOADER_IMAGE`); Makefile build target for the new image; the two rclone filter files updated as above. No new secrets.

## UI deltas (`dashboard/ui`)

- Enable the stubbed **Archived** tab with count badges; the existing list payload is split client-side by `archived_at`. Archived tab groups cards by recency (Last week / Last month buckets per mock).
- Card menu, archived: Rename, Duplicate (disabled), **Restore**, Delete. Active: existing items + enabled **Archive**, disabled while jobs are live (existing `activeJobCount` logic); server re-checks regardless. Notebook start/stop hidden on archived cards.
- Card click-to-wizard disabled when archived; `/experiments/$experimentId` deep-link for an archived experiment renders the archived notice + Restore action.
- Confirm dialogs: Archive (warns the local copy is deleted after verification; shows current size; notes a running notebook will be stopped), Restore (shows download size), Delete on archived (notes the S3 archive is also removed, irreversible).
- Transitional states (`archiving`/`restoring`/`*_failed`) are durable card states using existing spinner/alert patterns; no toast-only errors. Polling cadence unchanged; in-flight archive states keep the list polling on.

## Edge cases & failure semantics

- **Quiescence race:** a user can edit files via Jupyter mid-archive. `rclone check` gates deletion on what was verified; accepted, the confirm dialog warns that archiving freezes the experiment. Remounting RO is rejected as overkill.
- **API pod restart mid-archive:** status doc + live Job reconcile on next read; the worker is the only mutator and it is idempotent per attempt (fenced status writes).
- **Job killed (eviction/culling):** `preserve-on-stop` label protects from the notebook culler; otherwise reconciliation reports `failed` (`job_missing` analogue); retry resubmits under the deterministic name (existing terminal Job is deleted and awaited first).
- **Slow-to-schedule worker pod:** Pending counts as live (terminal-condition liveness), so a slow image pull or queue never flashes a `*_failed` banner or stops UI polling.
- **Restore into existing dir:** 409 unless the dir holds a non-completed restore status doc (retry sentinel), defending against clobbering foreign leftovers while keeping failed restores re-submittable. A failed Job submission (`create` raises or admission timeout) removes the queued status doc it wrote for archive (a submitted-but-never-started archive can't freeze at `archiving`); for restore it removes nothing, so the sentinel survives and the partially-restored dir stays re-submittable. Resubmission surfaces as 409 retry-later while the old Job is still terminating, not a generic 500.
- **S3 unreachable/misconfigured:** worker fails with `reason`; surface as durable alert; no local deletion ever happens before a successful `check`.
- **Purge orphans:** logged only; no sweeping/reconciliation loop (YAGNI). With the bisync filter correctly baked into the sidecar image, a purge also cannot be undone by a resurrecting bisync.
- **Local-only deployments (no `S3_BUCKET`):** endpoints return 400; the UI keeps menu items enabled but surfaces the durable error (capability is server-enforced; no runtime-config plumbing added).

## Testing

- **API pytest:** gate matrix for archive/restore (live job → 409, active upload → 409, running notebook → auto-stop + job submitted, already archived → 409, missing `S3_BUCKET` → 400, restore with existing dir → 409); status-doc round-trip + reconciliation (killed Job → `*_failed`; stale sentinel vs live Job → `restoring`; fencing); terminal-condition Job liveness; submission deletion-wait + sentinel preservation; schema serialization of `archived_at`/`archive_state`/snapshot fields incl. per-payload consistency of the stashed reconciliation; `DELETE` on archived submits purge. Migration additions follow the existing migration pattern (no `db.create_all`).
- **Worker:** script-level argument/state validation and the restore continuation matrix (failed/running sentinel resumes, completed/foreign doc refuses); rclone behavior is an integration concern and is exercised manually via `make demo` (seed an archived experiment + status doc in `_demo`, following existing demo seeding patterns).
- **UI vitest:** tab split/counts, archived card menu contents, confirm dialogs, transitional/failed states, deep-link archived notice.
- Repo gates before implementation is considered done: `make fix`, `make type-check`, `make knip`, `make test`, `make validate-charts`.

## Explicit non-goals

Per-simulation archiving; partial/single-file restore; archive browsing in the UI; tarball packaging; auto-archive policies/schedulers; orphan-archive garbage collection; changes to bisync loop logic or recovery paths; unblocking the existing Duplicate TODO.

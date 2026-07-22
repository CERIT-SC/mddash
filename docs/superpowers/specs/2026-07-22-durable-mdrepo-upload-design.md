# Durable MDRepo Upload Design

## Context

GitHub issue [#44](https://github.com/CERIT-SC/mddash/issues/44) requests that MDRepo uploads eventually run as Kubernetes Jobs and upload only files eligible for S3 synchronization. Its comments establish that OneData is unnecessary, the S3 filter should govern MDRepo uploads, and uploads lasting longer than the OAuth access-token lifetime must refresh their token.

The current Dashboard API creates an Invenio draft, saves `mdrepo_id`, and launches a daemon thread in its Gunicorn process. The thread recursively reads the experiment PVC and uploads files serially. A process restart, API container restart, or JupyterHub server stop terminates the thread. The remote draft can remain partially populated, no durable worker resumes it, and the UI treats the presence of `mdrepo_id` as success.

This design replaces that daemon thread with a Kubernetes Job in the existing per-user namespace. It is intentionally scoped to surviving a normal JupyterHub server stop. It does not guarantee recovery after the admitted upload pod is deleted or evicted while namespace quota is zero.

## Goals

- Continue an acknowledged MDRepo upload after the user stops their JupyterHub server and its API sidecar.
- Read upload content from the retained per-user PVC mounted into the Job.
- Apply the same rclone filter used by S3 synchronization.
- Refresh delegated MDRepo OAuth access tokens during long uploads.
- Serialize concurrent submissions and make retries idempotent after the MDRepo draft ID is persisted.
- Expose durable queued, running, completed, and failed upload states after an API restart.
- Make delegated OAuth credentials eligible for automatic garbage collection five minutes after the Job finishes.
- Preserve the existing behavior of opening the MDRepo draft as soon as the upload Job is accepted.

## Non-Goals

- Capturing an immutable snapshot of the experiment at the instant the user clicks Publish.
- Waiting for or reading from the local-to-S3 bisync cycle.
- Uploading objects directly from S3.
- Surviving deletion, eviction, or node loss of the upload pod after namespace quota reaches zero.
- Surviving administrator deletion of the user namespace or PVC.
- Introducing OneData, a central queue, or a new long-running upload service.
- Automating final publication of the Invenio draft.

## Selected Semantics

The uploader lists the current eligible files under the experiment directory on the PVC once when the Job starts. It uses the S3 synchronization filter, but does not depend on the S3 sidecar or remote bucket. Files can change after listing, so the worker verifies source identity, metadata, and checksum while reading and fails changed files rather than reporting an inconsistent upload as complete.

An upload is durably handed off only after the API receives confirmation that Kubernetes has admitted the Job pod. The API returns `202 Accepted` at that point. If the request is interrupted before that response, the client can safely repeat it; deterministic resource names and reconciliation complete or repair the same submission.

## Architecture

### Upload Worker

Add a dedicated, non-root MDRepo uploader image. Its only responsibilities are:

- list eligible files from the mounted experiment directory;
- inspect files already present in the existing Invenio draft;
- stream PVC files through Invenio's initialize, content, and commit operations;
- refresh the OAuth access token before expiry;
- retry transient operations with bounded exponential backoff; and
- write sanitized upload state to the PVC.

Move `rclone-filters.txt` to one shared build source consumed by both the S3-sync and uploader images, and keep the pinned rclone version identical in both images. Rclone evaluates the filter relative to `/mddash`, exactly as the bisync sidecar does, and the worker retains only entries whose first path component is the validated experiment ID. The filter version and SHA-256 hash are recorded in status and verified for both images in CI. Python streams the resulting files and writes status. The filter gains `**/.mdrepo-upload.json` and `**/.mdrepo-upload.json.tmp` exclusions so operational state is neither synchronized to S3 nor uploaded to MDRepo.

The worker mounts the existing per-user `ReadWriteMany` PVC at `/mddash`. It runs with the existing non-root security policy, dropped capabilities, `RuntimeDefault` seccomp, and explicit requests and limits.

### Kubernetes Resources

Each upload uses deterministic names derived from the local experiment and MDRepo draft IDs:

- one Kubernetes Job;
- one credential Secret owned by that Job; and
- one pod created by the Job controller.

The Job and pod template carry `mddash.io/preserve-on-stop=true` and labels identifying the experiment and unique attempt ID. Defaults are `restartPolicy: Never`, `backoffLimit: 0`, `activeDeadlineSeconds: 86400`, and `ttlSecondsAfterFinished: 300`; deployment configuration can override the two time limits. All recoverable network behavior is retried inside the worker so Kubernetes never starts a second process with stale rotated credentials or a different file listing. After the five-minute TTL, Kubernetes asynchronously deletes the finished Job and owner-bound Secret; controller delays mean deletion is eventual rather than bounded to exactly five minutes.

Submission uses a suspended Job to establish ownership safely:

1. Create or reconcile the suspended Job and obtain its UID.
2. Create or reconcile the Secret with an owner reference to that Job.
3. Unsuspend the Job.
4. Wait up to 30 seconds for its pod object to be admitted.
5. Return `202 Accepted`.

A failure before step 5 is not an acknowledged handoff. An admission timeout foreground-deletes the Job, waits for its pod and owner-bound Secret to disappear, and records a failed submission reason. Repeating the publish request reconciles a suspended submission or starts a new attempt without creating another draft.

Suspended Jobs carry a five-minute submission-lease annotation. API startup, each publish request, and the JupyterHub pre-spawn hook foreground-delete expired suspended submissions. The post-stop hook foreground-deletes every suspended or otherwise unadmitted upload Job because none has crossed the acknowledged handoff boundary. This bounds credential retention if the API exits between Secret creation and Job unsuspension.

### Server Shutdown And Quota

Kubernetes ResourceQuota is admission-time enforcement. Lowering CPU and memory quota below current usage does not evict already-created resources. It does prevent admission of replacement pods while the quota remains exceeded.

The existing `post_stop_hook` currently deletes every pod in the user namespace before or while reducing quota to zero. It must list candidate preserved pods and retain only pods owned by a labeled MDRepo upload Job whose attempt ID, uploader image, service account, and experiment identity match the expected manifest. All other pods are deleted. Once an upload pod has been admitted, that pod continues to run after quota becomes zero. Quota patch failures are logged explicitly but do not trigger deletion of a preserved uploader.

The durability guarantee starts at the `202 Accepted` response because that response is delayed until pod admission. The worker handles retries inside that admitted pod. A new pod cannot be created after quota reaches zero, so process crashes, pod deletion, eviction, and node-loss recovery remain explicitly unsupported by this design.

### Credentials And RBAC

The short-lived Secret contains only values required by the worker:

- MDRepo access token, refresh token, access-token expiry, client ID, and client secret;
- the MDRepo API URL and record collection where appropriate.

The Secret is mounted as read-only data or exposed through `secretKeyRef`; credentials must not appear as literal values in the Job specification, labels, annotations, logs, status documents, or API responses.

The user pod's existing default service account is the submitter. Its namespace Role gains only `create`, `patch`, and `delete` on Secrets; it already manages Jobs in that user's namespace. The notebook and API sidecars already share this namespace identity and the API already receives the MDRepo client secret, so the per-user pod and namespace remain one trust boundary. This design does not grant cross-tenant access, but it does not attempt to isolate platform credentials from code run by that same user. Achieving that stronger boundary requires moving the API to a separate pod identity or introducing a trusted broker, both outside this design. The uploader Job uses a dedicated `mdrepo-uploader` service account with `automountServiceAccountToken: false` and no RBAC bindings. Kubelet can mount the referenced Secret without granting the uploader Kubernetes API access.

## API Flow

`POST /experiments/<experiment_id>/publish` retains synchronous metadata extraction and Invenio draft creation. Its Invenio path changes as follows:

1. Validate or refresh the user's MDRepo token.
2. Atomically reserve publication on the experiment row with a conditional database update, recording `creating`, an attempt ID, and a short creation lease. A concurrent request that loses this compare-and-set returns the existing operation instead of calling MDRepo.
3. If `mdrepo_id` is absent, extract metadata and create one Invenio draft, then persist its ID immediately. If it already identifies a draft with an incomplete or failed upload, reuse it.
4. Atomically write the attempt's queued state in the experiment directory on the PVC.
5. Reconcile and start the Secret and Job.
6. Wait for the upload pod to be admitted.
7. Mark the durable handoff on the experiment row and return `202 Accepted` with the existing draft metadata, draft URL, upload ID, and queued/running state.

The experiment model gains upload attempt, state, and creation-lease fields through a database migration. They serialize concurrent Gunicorn threads and survive process restart. A published MDRepo record cannot be retried as a draft upload. An active upload returns its existing identity and does not rewrite status. A failed upload can be retried through the same publish operation and targets the same draft. Before retrying, the API foreground-deletes the old Job, waits for its pod and Secret to disappear, and creates a new attempt ID.

Add `GET /experiments/<experiment_id>/publish/status`. It merges the durable PVC state document with live Job state when the Job still exists. The PVC document is authoritative for completed worker output; Kubernetes is authoritative for pending, active, and controller-level failure conditions that prevented the worker from recording a terminal state.

If the status file remains `queued` or `running` but its Job no longer exists, the endpoint reports `failed` with reason `job_missing`; it never leaves a stale nonterminal state after Job TTL cleanup.

Publish, status, retry, and experiment-deletion operations reconcile the experiment row from the attempt-fenced PVC and live Job state before applying active-attempt rules. A terminal state updates the row only when its attempt ID still matches, preventing an old result from closing a newer attempt. The worker never needs database or API access; reconciliation occurs when the user next interacts with the API.

## Worker Flow

1. Write `running` status with start time and empty counters.
2. List `/mddash` recursively using the canonical rclone filter, retain the selected experiment prefix, and record each file's size, modification time, and inode identity.
3. Fail with a clear status if no eligible files exist.
4. Fetch the Invenio draft file inventory.
5. For each local file, compute the MD5 checksum used by Invenio and compare its relative key, size, and checksum with the committed draft entry.
6. Skip an already committed matching file.
7. Remove or replace incomplete and mismatched entries using supported Invenio draft-file operations.
8. Initialize the key, stream content from the PVC, and commit it.
9. Verify the open file's size, modification time, inode identity, and streamed MD5 against the pre-upload values.
10. Update bounded progress state after each committed file.
11. Write `completed` only after every listed file is committed successfully.

The local listing is fixed for that Job attempt. New files created after listing are not part of that publication attempt. A listed file that changes while it is read fails that attempt and is safely retried from its new state. Completion means that the bytes read for every listed file were committed; it does not create an immutable snapshot or prevent a user or bisync from changing a file afterward.

Remote draft files that are absent from the local listing are left untouched because a user may add them directly in MDRepo. Completion therefore guarantees that the filtered local listing is present in the draft, not that the draft contains no additional files.

## OAuth Refresh

The worker owns a request-independent token manager initialized from the Secret. Before each MDRepo operation it refreshes the access token when it is expired or within the configured safety window. A `401 Unauthorized` causes one refresh and replay when a refresh token is available.

Refreshed tokens remain in worker memory. Refresh-token rotation is honored for the lifetime of that process. Kubernetes does not restart the worker, and replacement-process recovery after quota reaches zero is outside scope, so persisting rotated refresh tokens back to Kubernetes is unnecessary for this design.

A single content PUT that began with a valid token is allowed to finish. If MDRepo rejects a later commit because the token expired, the worker refreshes and retries the appropriate idempotent operation.

## Idempotency And Retries

The local experiment has at most one active MDRepo draft and one active attempt. Deterministic Kubernetes names include the attempt ID and prevent duplicate resources for an idempotently repeated request. A retry returns the existing Job while it is active, reconciles it while it is suspended, or foreground-deletes its terminal resources before creating a new attempt.

Network timeouts, connection failures, `429`, and retryable `5xx` responses use bounded exponential backoff. Authentication failures use the refresh flow rather than generic retries. Validation failures, source-file changes, and non-retryable `4xx` responses fail the affected file immediately.

The worker attempts all eligible files where continuing is safe, records a bounded list of failed keys, and exits non-zero if any file remains unresolved. It never reports partial success as completion. A retry re-reads both the PVC and the draft inventory, skips committed matching files, and repairs incomplete entries.

## Durable Status

The status file lives inside the retained experiment directory:

```text
/mddash/<experiment_id>/.mdrepo-upload.json
```

The state document contains:

- attempt ID, local experiment ID, MDRepo draft ID, and Kubernetes Job name;
- state: `queued`, `running`, `completed`, or `failed`;
- a machine-readable reason code for admission, authentication, source, remote, timeout, and controller failures;
- creation, start, update, and terminal timestamps as applicable;
- total and completed file counts and byte counts;
- a bounded set of failed file keys and sanitized error summaries; and
- schema and filter versions plus the filter SHA-256 hash.

It never contains OAuth tokens, request headers, stack traces, or raw remote response bodies. Until pod admission the API is the only writer, including admission-timeout failure after it has confirmed that any raced pod is terminated. After pod admission the worker is the only writer. Every worker update verifies that the on-disk attempt ID matches its own; a mismatch fences the stale worker and prevents state regression. Writers create a complete attempt-specific temporary file, flush and fsync it, then atomically rename it over the status file. If a status write fails, the worker retries it but does not repeat an already committed MDRepo file solely because progress reporting failed.

## UI Behavior

The UI stops treating `mdrepo_id != null` as proof that file upload succeeded. It displays distinct draft/upload states and polls the publish-status endpoint while queued or running.

After `POST /publish` returns, the UI immediately opens the MDRepo draft, preserving current behavior. It also continues to show upload progress and a warning that the draft's files are incomplete until the worker reports completion. Failed state exposes a retry action that invokes the same idempotent publish endpoint.

## Error Cases

- Draft creation failure creates neither a Secret nor a Job.
- Secret or Job creation failure preserves the existing draft and records a retryable submission failure without creating another draft.
- API termination before `202 Accepted` leaves an unacknowledged operation that the next request or lifecycle-hook lease cleanup reconciles.
- API termination after MDRepo creates a draft but before its ID is persisted can leave an orphan remote draft; see Accepted Limitations.
- Missing experiment directories and empty eligible file sets fail rather than producing a misleading successful upload.
- Experiment deletion through the API is rejected while an upload is queued or running.
- Source files changed while being read fail validation and require an idempotent retry; later changes are outside the snapshot guarantee.
- Token refresh failure fails the Job with a reauthentication-required status.
- A draft published or deleted during transfer fails subsequent draft-file operations and produces a clear terminal status.
- Unresolved per-file errors fail the entire Job even if other files committed successfully.
- Worker crashes and upload-pod eviction after quota reaches zero leave the Job unable to obtain a replacement process or pod until the user submits a new attempt after quota is restored. The status endpoint reports the live Kubernetes condition when available.

## Testing

### Worker Unit Tests

- canonical rclone filter use and exclusion parity;
- recursive PVC listing and empty-directory handling;
- nested and URL-sensitive file keys;
- initialize, stream, and commit ordering;
- committed-file skipping and incomplete-file replacement;
- preservation of draft files that are not in the local listing;
- transient retries, terminal errors, and aggregate failure;
- proactive refresh and refresh-on-401 behavior;
- source-file mutation detection;
- atomic and attempt-fenced queued/running/completed/failed state writes; and
- credential and remote-response redaction.

### API Unit And Integration Tests

- first publication creates exactly one draft;
- repeated and interrupted submissions reconcile deterministic resources;
- concurrent publish requests create only one active local operation;
- failed uploads retry against the same draft;
- Secret values are referenced, never embedded in Job manifests;
- suspended Job, owner reference, unsuspend, and pod-admission ordering;
- bounded admission timeout and foreground cleanup;
- expired submission-lease cleanup at startup and lifecycle hooks;
- `202 Accepted` is returned only after pod admission;
- active and completed status merge behavior;
- attempt-fenced terminal-state reconciliation into the experiment row;
- retry waits for old resources to terminate and creates a new attempt ID;
- experiment deletion is blocked during active upload; and
- published records reject upload retries.

### Helm And Kubernetes Tests

- uploader image configuration, resources, security context, and RWX PVC mount;
- namespace-local submitter RBAC and tokenless uploader service account;
- preserve-on-stop labels on Job and pod template;
- post-stop deletion excludes upload pods;
- quota is still reduced to zero after normal server stop;
- Job and Secret TTL ownership cleanup; and
- an admitted upload pod remains after invoking `post_stop_hook` and completes while quota is zero.

### UI Tests

- draft opens immediately after Job acceptance;
- queued and running progress are polled and rendered;
- completion and failure are distinct from draft existence;
- failed upload offers an idempotent retry; and
- the incomplete-files warning remains visible while the draft is openable.

## Acceptance Criteria

- No MDRepo upload runs in a Flask daemon thread.
- The upload Job mounts the retained per-user RWX PVC and does not require S3 credentials.
- After `POST /publish` returns `202`, stopping the JupyterHub server does not delete the upload pod.
- The admitted upload pod completes with namespace CPU and memory quota set to zero.
- Only files under the selected experiment directory that pass the canonical rclone filter are considered.
- A transfer longer than one access-token lifetime can refresh OAuth credentials and continue.
- Concurrent publish requests are serialized, and retries after `mdrepo_id` persistence reuse that draft.
- Kubernetes does not restart a failed uploader process; application-level retries remain inside one process and user retry creates a fenced new attempt.
- Partial uploads are reported as failed, not completed.
- Upload status remains readable from the PVC after API restart and after Kubernetes TTL cleanup.
- Job manifests, status files, API responses, and logs contain no OAuth credentials.

## Accepted Limitations

The selected same-namespace design relies on Kubernetes not evicting already-admitted resources when ResourceQuota is lowered. If the upload pod itself is subsequently deleted or evicted, the Job controller cannot create a replacement while quota is zero. Supporting that stronger guarantee requires either retaining upload-sized quota after server stop or moving execution to a namespace with an independent lifecycle.

MDRepo draft creation and the local SQLite update cannot be one atomic transaction. The creation lease prevents concurrent requests from creating duplicate drafts, but a process death after MDRepo accepts creation and before `mdrepo_id` is persisted can leave an orphan remote draft. Eliminating this narrow failure window requires MDRepo to support an idempotency key or a searchable MDDash operation identifier.

The notebook and API sidecars share one Kubernetes pod and service-account trust boundary today. Namespace-local code can already exercise the pod's Kubernetes permissions and reach API-sidecar configuration. This design prevents cross-tenant access and gives the uploader no API token, but isolating the platform OAuth client secret from the user's notebook requires separating the API identity or adding a trusted broker.

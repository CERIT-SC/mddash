# Durable MDRepo Upload Design

## Context

GitHub issue [#44](https://github.com/CERIT-SC/mddash/issues/44) requests that MDRepo uploads eventually run as Kubernetes Jobs and upload only files synchronized to S3. Its comments also establish that OneData is unnecessary, the S3 filter should govern MDRepo uploads, and uploads lasting longer than the OAuth access-token lifetime must refresh their token.

The current Dashboard API creates an Invenio draft, saves `mdrepo_id`, and launches a daemon thread in its Gunicorn process. The thread recursively reads the experiment PVC and uploads files serially. A process restart, API container restart, or JupyterHub server stop terminates the thread. The remote draft can remain partially populated, no durable worker resumes it, and the UI treats the presence of `mdrepo_id` as success.

This design replaces that daemon thread with a Kubernetes Job in the existing per-user namespace. It is intentionally scoped to surviving a normal JupyterHub server stop. It does not guarantee recovery after the admitted upload pod is deleted or evicted while namespace quota is zero.

## Goals

- Continue an acknowledged MDRepo upload after the user stops their JupyterHub server and its API sidecar.
- Read upload content directly from the experiment's S3 prefix, without mounting the user PVC.
- Apply the same rclone filter used by S3 synchronization.
- Refresh delegated MDRepo OAuth access tokens during long uploads.
- Make submission and retries idempotent so they do not create duplicate MDRepo drafts.
- Expose durable queued, running, completed, and failed upload states after an API restart.
- Remove delegated OAuth credentials automatically after the Job finishes.
- Preserve the existing behavior of opening the MDRepo draft as soon as the upload Job is accepted.

## Non-Goals

- Capturing the exact local file set at the instant the user clicks Publish.
- Waiting for the local-to-S3 bisync cycle before submission.
- Uploading files from the PVC.
- Surviving deletion, eviction, or node loss of the upload pod after namespace quota reaches zero.
- Introducing OneData, a central queue, or a new long-running upload service.
- Automating final publication of the Invenio draft.

## Selected Semantics

The uploader lists the current S3 contents under the experiment prefix once when the Job starts. Files that have not reached S3 are not included, and stale S3 objects can be included. This is an accepted consequence of selecting current-S3 semantics rather than a click-time snapshot.

An upload is durably handed off only after the API receives confirmation that Kubernetes has admitted the Job pod. The API returns `202 Accepted` at that point. If the request is interrupted before that response, the client can safely repeat it; deterministic resource names and reconciliation complete or repair the same submission.

## Architecture

### Upload Worker

Add a dedicated, non-root MDRepo uploader image. Its only responsibilities are:

- list eligible objects from the configured S3 experiment prefix;
- inspect files already present in the existing Invenio draft;
- stream S3 objects through Invenio's initialize, content, and commit operations;
- refresh the OAuth access token before expiry;
- retry transient operations with bounded exponential backoff; and
- write sanitized upload state to S3.

The image includes the pinned rclone version already used by `dashboard/s3-sync` and consumes the same `rclone-filters.txt`. Rclone is the authority for filtering and listing; the worker uses boto3 to stream the resulting object keys and write status. The Dashboard API also uses boto3 to create queued state and read status. The filter gains an exclusion for the reserved MDDash operational-state prefix so status records never bisync to the PVC or enter a publication.

The worker runs with the existing non-root security policy, dropped capabilities, `RuntimeDefault` seccomp, explicit requests and limits, and no PVC mount.

### Kubernetes Resources

Each upload uses deterministic names derived from the local experiment and MDRepo draft IDs:

- one Kubernetes Job;
- one credential Secret owned by that Job; and
- one pod created by the Job controller.

The Job and pod template carry `mddash.io/preserve-on-stop=true` and labels identifying the experiment and upload. Defaults are `restartPolicy: OnFailure`, `backoffLimit: 3`, `activeDeadlineSeconds: 86400`, and `ttlSecondsAfterFinished: 3600`; deployment configuration can override the two time limits. The TTL deletes the finished Job and owner-bound Secret.

Submission uses a suspended Job to establish ownership safely:

1. Create or reconcile the suspended Job and obtain its UID.
2. Create or reconcile the Secret with an owner reference to that Job.
3. Unsuspend the Job.
4. Wait for its pod object to be admitted.
5. Return `202 Accepted`.

A failure before step 5 is not an acknowledged handoff. Repeating the publish request reconciles the suspended Job, Secret, draft, and pod rather than creating duplicate resources.

### Server Shutdown And Quota

Kubernetes ResourceQuota is admission-time enforcement. Lowering CPU and memory quota below current usage does not evict already-created resources. It does prevent admission of replacement pods while the quota remains exceeded.

The existing `post_stop_hook` currently deletes every pod in the user namespace before or while reducing quota to zero. It must instead delete only pods that do not have `mddash.io/preserve-on-stop=true`. Once an upload pod has been admitted, that pod continues to run after quota becomes zero.

The durability guarantee starts at the `202 Accepted` response because that response is delayed until pod admission. A container restart inside the admitted pod can continue according to the pod restart policy. A new pod cannot be created after quota reaches zero, so pod deletion, eviction, and node-loss recovery remain explicitly unsupported by this design.

### Credentials And RBAC

The short-lived Secret contains only values required by the worker:

- MDRepo access token, refresh token, access-token expiry, client ID, and client secret;
- S3 endpoint, bucket, access key, and secret key; and
- the MDRepo API URL and record collection where appropriate.

The Secret is mounted as read-only data or exposed through `secretKeyRef`; credentials must not appear as literal values in the Job specification, labels, annotations, logs, status documents, or API responses.

The per-user default service account needs narrowly scoped verbs to create and reconcile Secrets in its own namespace in addition to its existing Job permissions. Upload resources remain inside that user's namespace, avoiding cross-tenant access to a shared admin namespace. The upload pod receives no Kubernetes API permissions beyond those required by its execution.

## API Flow

`POST /experiments/<experiment_id>/publish` retains synchronous metadata extraction and Invenio draft creation. Its Invenio path changes as follows:

1. Validate or refresh the user's MDRepo token.
2. If `mdrepo_id` is absent, extract metadata and create one Invenio draft, then persist its ID.
3. If `mdrepo_id` already identifies a draft with an incomplete or failed upload, reuse it.
4. Write a queued state record to the reserved S3 status key.
5. Reconcile and start the Secret and Job.
6. Wait for the upload pod to be admitted.
7. Return `202 Accepted` with the existing draft metadata, draft URL, upload ID, and queued/running state.

A published MDRepo record cannot be retried as a draft upload. An active upload returns its existing identity rather than creating another Job. A failed upload can be retried through the same publish operation and targets the same draft.

Add `GET /experiments/<experiment_id>/publish/status`. It merges the durable S3 state document with live Job state when the Job still exists. S3 is authoritative for completed worker output; Kubernetes is authoritative for pending, active, and controller-level failure conditions that prevented the worker from recording a terminal state.

## Worker Flow

1. Write `running` status with start time and empty counters.
2. List the experiment's current S3 prefix using the canonical rclone filter.
3. Fail with a clear status if no eligible objects exist.
4. Fetch the Invenio draft file inventory.
5. For each S3 object, compare the key and available size/checksum metadata with the draft entry.
6. Skip an already committed matching file.
7. Remove or replace incomplete and mismatched entries using supported Invenio draft-file operations.
8. Initialize the key, stream content from S3, and commit it.
9. Update bounded progress state after each committed file.
10. Write `completed` only after every listed object is committed successfully.

The S3 listing is fixed for that Job attempt. Changes made to S3 after listing are handled only by a later retry or publication attempt.

## OAuth Refresh

The worker owns a request-independent token manager initialized from the Secret. Before each MDRepo operation it refreshes the access token when it is expired or within the configured safety window. A `401 Unauthorized` causes one refresh and replay when a refresh token is available.

Refreshed tokens remain in worker memory. Refresh-token rotation is honored for the lifetime of that pod. Because replacement-pod recovery after quota reaches zero is outside scope, persisting rotated refresh tokens back to Kubernetes is unnecessary for this design.

A single content PUT that began with a valid token is allowed to finish. If MDRepo rejects a later commit because the token expired, the worker refreshes and retries the appropriate idempotent operation.

## Idempotency And Retries

The local experiment has at most one active MDRepo draft. Deterministic Kubernetes names prevent duplicate active Jobs for the same draft. A retry returns the existing Job while it is active, reconciles it while it is suspended, or deletes and recreates the same-named Job and Secret after a terminal failure.

Network timeouts, connection failures, `429`, and retryable `5xx` responses use bounded exponential backoff. Authentication failures use the refresh flow rather than generic retries. Validation failures and non-retryable `4xx` responses fail the affected file immediately.

The worker attempts all eligible files where continuing is safe, records a bounded list of failed keys, and exits non-zero if any file remains unresolved. It never reports partial success as completion. A retry re-reads both S3 and the draft inventory, skips committed matching files, and repairs incomplete entries.

## Durable Status

The reserved S3 key is outside experiment prefixes, for example:

```text
_mddash/mdrepo-uploads/<experiment_id>.json
```

The state document contains:

- upload ID, local experiment ID, MDRepo draft ID, and Kubernetes Job name;
- state: `queued`, `running`, `completed`, or `failed`;
- creation, start, update, and terminal timestamps as applicable;
- total and completed file counts and byte counts;
- a bounded set of failed object keys and sanitized error summaries; and
- a schema version.

It never contains OAuth tokens, S3 credentials, request headers, stack traces, or raw remote response bodies. Writes replace the complete document atomically at the object level. If a status write fails, the worker retries it but does not repeat an already committed MDRepo file solely because progress reporting failed.

## UI Behavior

The UI stops treating `mdrepo_id != null` as proof that file upload succeeded. It displays distinct draft/upload states and polls the publish-status endpoint while queued or running.

After `POST /publish` returns, the UI immediately opens the MDRepo draft, preserving current behavior. It also continues to show upload progress and a warning that the draft's files are incomplete until the worker reports completion. Failed state exposes a retry action that invokes the same idempotent publish endpoint.

## Error Cases

- Draft creation failure creates neither a Secret nor a Job.
- Secret or Job creation failure preserves the existing draft and records a retryable submission failure without creating another draft.
- API termination before `202 Accepted` leaves an unacknowledged operation that the same request can reconcile later.
- Missing or empty S3 experiment prefixes fail rather than producing a misleading successful upload.
- Token refresh failure fails the Job with a reauthentication-required status.
- A draft published or deleted during transfer fails subsequent draft-file operations and produces a clear terminal status.
- Unresolved per-file errors fail the entire Job even if other files committed successfully.
- Upload-pod eviction after quota reaches zero leaves the Job unable to obtain a replacement pod until quota is restored. The status endpoint reports the live Kubernetes condition when available.

## Testing

### Worker Unit Tests

- canonical rclone filter use and exclusion parity;
- current-prefix listing and empty-prefix handling;
- nested and URL-sensitive object keys;
- initialize, stream, and commit ordering;
- committed-file skipping and incomplete-file replacement;
- transient retries, terminal errors, and aggregate failure;
- proactive refresh and refresh-on-401 behavior;
- queued/running/completed/failed state documents; and
- credential and remote-response redaction.

### API Unit And Integration Tests

- first publication creates exactly one draft;
- repeated and interrupted submissions reconcile deterministic resources;
- failed uploads retry against the same draft;
- Secret values are referenced, never embedded in Job manifests;
- suspended Job, owner reference, unsuspend, and pod-admission ordering;
- `202 Accepted` is returned only after pod admission;
- active and completed status merge behavior; and
- published records reject upload retries.

### Helm And Kubernetes Tests

- uploader image configuration, resources, and security context;
- namespace-local Secret and Job RBAC;
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
- After `POST /publish` returns `202`, stopping the JupyterHub server does not delete the upload pod.
- The admitted upload pod completes with namespace CPU and memory quota set to zero.
- Only objects under the selected experiment's current S3 prefix that pass the canonical rclone filter are considered.
- A transfer longer than one access-token lifetime can refresh OAuth credentials and continue.
- Repeating a failed or interrupted publish request does not create a second MDRepo draft.
- Partial uploads are reported as failed, not completed.
- Upload status remains readable after API restart and after Kubernetes TTL cleanup.
- Job manifests, status objects, API responses, and logs contain no OAuth or S3 credentials.

## Accepted Limitation

The selected same-namespace design relies on Kubernetes not evicting already-admitted resources when ResourceQuota is lowered. If the upload pod itself is subsequently deleted or evicted, the Job controller cannot create a replacement while quota is zero. Supporting that stronger guarantee requires either retaining upload-sized quota after server stop or moving execution to a namespace with an independent lifecycle.

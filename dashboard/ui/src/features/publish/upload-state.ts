import type { PublishStatus } from "@/api/generated/models"

/**
 * Upload lifecycle helpers for the durable MDRepo upload status document.
 * The OpenAPI schema keeps `upload_state` a plain string, so these mirror the
 * API's UploadState enum values without restating a generated type.
 */

/** Non-terminal states — the upload Job keeps being polled while in either. */
export function uploadActive(state: string | null | undefined): boolean {
  return state === "queued" || state === "running"
}

/** Short human-readable label for the upload state chip; unknown states pass through. */
export function uploadStateLabel(state: string): string {
  switch (state) {
    case "queued":
      return "Queued"
    case "running":
      return "Uploading"
    case "completed":
      return "Completed"
    case "failed":
      return "Failed"
    default:
      return state
  }
}

/** TanStack Query refetchInterval: poll only while the status doc reports an active upload. */
export function pollWhileUploadActive(pollMs: number) {
  return (query: { state: { data: unknown } }): number | false => {
    const data = query.state.data as { status: number; data: PublishStatus } | undefined
    return data?.status === 200 && uploadActive(data.data.upload_state) ? pollMs : false
  }
}

/** Human-readable copy for the API's failure reason codes (upload/status.py); null when none is known. */
const FAILURE_REASONS: Record<string, string> = {
  auth: "Authentication with MDRepo failed; reconnect to MDRepo and retry.",
  source: "Some source files could not be read; check the files and retry.",
  remote: "MDRepo rejected an uploaded file; retry, or contact support if it persists.",
  timeout: "The upload timed out; retry the upload.",
  controller: "The upload job failed unexpectedly; retry the upload.",
  job_missing: "The upload job is no longer running; retry the upload.",
  empty: "There was nothing to upload; add files to the experiment first.",
}

export function uploadFailureReason(reason: string | null | undefined): string | null {
  if (typeof reason !== "string" || reason === "") return null
  return FAILURE_REASONS[reason] ?? null
}

import type { PodStatus } from "@/api/generated/models"

// Any non-down pod counts as active; shared by the dashboard's notebook grouping and the card dot.
const NOTEBOOK_ACTIVE: ReadonlySet<PodStatus> = new Set(["RUNNING", "PENDING", "UNKNOWN", "TERMINATING"])

export function isNotebookActive(status: PodStatus | undefined): boolean {
  return status !== undefined && NOTEBOOK_ACTIVE.has(status)
}

import type { Experiment } from "@/api/generated/models"
import { relativeTime } from "@/shared/format"

export const IN_FLIGHT: ReadonlySet<Experiment["archive_state"]> = new Set(["archiving", "restoring"])
const FAILED: ReadonlySet<Experiment["archive_state"]> = new Set(["archive_failed", "restore_failed"])

export function isArchived(experiment: Experiment): boolean {
  return experiment.archived_at !== null
}

export function isArchiving(experiment: Experiment): boolean {
  return experiment.archive_state !== null && IN_FLIGHT.has(experiment.archive_state)
}

export function isArchivedFailed(experiment: Experiment): boolean {
  return experiment.archive_state !== null && FAILED.has(experiment.archive_state)
}

const REASON_LABELS: Record<string, string> = {
  "seed-copy": "initial copy failed",
  "delta-sync": "syncing changes failed",
  check: "verification failed",
  copy: "copying failed",
  "archive-empty": "the archive was empty",
  "target-exists": "a local folder was in the way",
  "source-missing": "the local folder was missing",
}

export function archiveReasonLabel(reason: string | null | undefined): string | null {
  return reason ? (REASON_LABELS[reason] ?? null) : null
}

// Transitional/archived states replace the "Active …" idle label; restore_failed counts as archived.
export function archiveStateLabel(experiment: Experiment): string | null {
  switch (experiment.archive_state) {
    case "archiving":
      return "Archiving…"
    case "restoring":
      return "Restoring…"
    case "archived":
    case "restore_failed":
      return `Archived ${relativeTime(experiment.archived_at ?? experiment.updated_at)}`
    default:
      return null
  }
}

const DAY_MS = 86_400_000

// Mock-grouped buckets: the archived tab reads as a retention timeline.
export function groupByArchiveRecency(experiments: Experiment[]): { label: string; experiments: Experiment[] }[] {
  const now = Date.now()
  const buckets: { label: string; cutoffMs: number; experiments: Experiment[] }[] = [
    { label: "Last 7 days", cutoffMs: 7 * DAY_MS, experiments: [] },
    { label: "Last month", cutoffMs: 31 * DAY_MS, experiments: [] },
  ]
  const older: Experiment[] = []
  for (const experiment of experiments) {
    const age = now - new Date(experiment.archived_at ?? experiment.updated_at).getTime()
    const bucket = buckets.find((candidate) => age <= candidate.cutoffMs)
    if (bucket) bucket.experiments.push(experiment)
    else older.push(experiment)
  }
  return [
    ...buckets.filter((bucket) => bucket.experiments.length > 0),
    ...(older.length > 0 ? [{ label: "Older", experiments: older }] : []),
  ].map(({ label, experiments }) => ({ label, experiments }))
}

import {
  getJobStatusVariant,
  getPodStatusVariant,
  type JobStatus,
  type PodStatus,
  type StatusVariant,
  type UploadState,
} from "@/util/types"

const PENDING_BADGE_CLASS =
  "border-yellow-400 bg-transparent text-yellow-700 dark:border-yellow-600 dark:text-yellow-300"

export function statusBadgeClass(variant: StatusVariant): string {
  switch (variant) {
    case "success":
      return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    case "warning":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
    case "info":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
    case "destructive":
      return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
    case "secondary":
      return "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
    default:
      return ""
  }
}

export function isActiveJobStatus(status: JobStatus): boolean {
  return status === "PENDING" || status === "RUNNING"
}

export function jobStatusBadgeClass(status: JobStatus): string {
  if (status === "PENDING") return PENDING_BADGE_CLASS
  return statusBadgeClass(getJobStatusVariant(status))
}

export function isActivePodStatus(status: PodStatus): boolean {
  return status === "PENDING" || status === "INITIALIZING" || status === "TERMINATING"
}

export function podStatusBadgeClass(status: PodStatus): string {
  if (status === "PENDING") return PENDING_BADGE_CLASS
  return statusBadgeClass(getPodStatusVariant(status))
}

export function isActiveUploadState(status: UploadState): boolean {
  return status === "queued" || status === "running"
}

export function uploadStatusBadgeClass(status: UploadState): string {
  if (status === "queued") return PENDING_BADGE_CLASS
  if (status === "running") return statusBadgeClass("warning")
  if (status === "completed") return statusBadgeClass("success")
  return statusBadgeClass("destructive")
}

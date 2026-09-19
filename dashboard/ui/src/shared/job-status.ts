import { JobStatus } from "@/api/generated/models"

/**
 * User-facing label per job status, shared by surfaces that print a status outside
 * the run headline (run history, lists). Keep copy aligned with `RunProgress`.
 */
export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  [JobStatus.UNKNOWN]: "Preparing",
  [JobStatus.PENDING]: "Pending",
  [JobStatus.RUNNING]: "Running",
  [JobStatus.FINISHED]: "Finished",
  [JobStatus.ERROR]: "Failed",
  [JobStatus.STOPPED]: "Stopped",
}

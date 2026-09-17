import type { AnalysisJob, Experiment } from "@/api/generated/models"

// UNKNOWN is live server-side (transient upstream failure) — don't freeze on
// it. Sim/tuner payloads embed is_live; analysis carries only a plain status.
const LIVE_ANALYSIS_STATUSES = new Set<AnalysisJob["status"]>(["PENDING", "RUNNING", "UNKNOWN"])

export function isAnalysisJobLive(job: AnalysisJob): boolean {
  return LIVE_ANALYSIS_STATUSES.has(job.status)
}

export function hasLiveWork(experiment: Experiment): boolean {
  return (
    experiment.simulation_jobs.some((job) => job.is_live) ||
    experiment.tuner_jobs.some((job) => job.is_live) ||
    experiment.analysis_jobs.some(isAnalysisJobLive)
  )
}

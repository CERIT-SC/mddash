import type { AnalysisJob, Experiment } from "@/api/generated/models"

// UNKNOWN is live server-side (transient upstream failure): cards and the list
// poll must not freeze on it. Sim/tuner payloads embed the server's is_live;
// analysis payloads carry only a plain status, so the set lives here.
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

import type { Engine } from "./const"

export interface Experiment {
  id: string
  created_at: string
  updated_at: string
  name: string
  source_message: string | null
  notebooks_repo: string | null
  mdrepo_id: string | null
  mdrepo_record_url: string | null
  step: number
  status: string
  engine: Engine
  notebook: Notebook
  tuner_jobs: TunerJob[]
  simulation_jobs: SimulationJob[]
}

export type NotebookTier = "1x" | "2x" | "4x"

export interface Notebook {
  id: number
  experiment_id: string
  token: string
  path: string
  status: PodStatus
  tier: NotebookTier | null
  gpu: boolean
}

export interface TierInfo {
  value: NotebookTier
  cpuLimit: string
  memoryLimit: string
}

export interface NotebookConfig {
  tiers: TierInfo[]
  defaultTier: NotebookTier
}

export interface TunerJob {
  id: string
  experiment_id: string
  engine: Engine
  tpr_name: string
  inpcrd_name: string | null
  mdin_name: string | null
  tuner_status: JobStatus | null
  error_message: string | null
  created_at: string
  is_stopped: boolean
  trials: GmxTunerTrial[] | AmberTunerTrial[]
}

export interface GmxTunerTrial {
  id: string
  status: JobStatus
  np: number
  ntomp: number
  pme: DeviceType
  nb: DeviceType
  performance: number | null
}

export interface AmberTunerTrial {
  id: string
  status: JobStatus
  np: number
  ntomp: number
  binary: AmberBinary
  ewald: EwaldPreset
  performance: number | null
}

export type DeviceType = "auto" | "cpu" | "gpu"
export type AmberBinary = "pmemd.cuda" | "pmemd.MPI"
export type EwaldPreset = "default" | "optimized"

// Discriminated union for simulation jobs
export type SimulationJob = GromacsJob | AmberJob

export interface GromacsJob {
  id: string
  experiment_id: string
  created_at: string
  engine: "GMX"
  tpr_name: string
  pme: DeviceType
  nb: DeviceType
  np: number
  ntomp: number
  extra_args: string
  status: JobStatus
  start_timestamp: number | null
  finish_timestamp: number | null
  nsteps: number | null
  performance: number | null
  nsteps_done: number | null
  estimated_time: number | null
}

export interface AmberJob {
  id: string
  experiment_id: string
  created_at: string
  engine: "AMBER"
  prmtop_name: string
  inpcrd_name: string
  mdin_name: string
  binary: AmberBinary
  ewald: EwaldPreset
  np: number
  ntomp: number
  extra_args: string
  status: JobStatus
  start_timestamp: number | null
  finish_timestamp: number | null
  nsteps: number | null
  performance: number | null
  nsteps_done: number | null
  estimated_time: number | null
}

export interface ResourceUsage {
  requests: {
    cpu: number
    memory: number
    storage: number | null
  }
  limits: {
    cpu: number
    memory: number
    storage: number
  }
}

export interface FileOption {
  name: string
  path: string
  url: string
  size: number
}

export type StatusVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info"

export type PodStatus =
  | "RUNNING"
  | "PENDING"
  | "INITIALIZING"
  | "TERMINATED"
  | "ERROR"
  | "TERMINATING"
  | "DOWN"
  | "UNKNOWN"

export function getPodStatusVariant(status: PodStatus): StatusVariant {
  switch (status) {
    case "RUNNING":
      return "success"
    case "PENDING":
    case "INITIALIZING":
    case "TERMINATING":
      return "warning"
    case "TERMINATED":
      return "info"
    case "ERROR":
    case "DOWN":
      return "destructive"
    case "UNKNOWN":
      return "secondary"
  }
}

export type JobStatus = "UNKNOWN" | "PENDING" | "RUNNING" | "TERMINATED" | "ERROR"

export function getJobStatusVariant(status: JobStatus): StatusVariant {
  switch (status) {
    case "UNKNOWN":
      return "secondary"
    case "RUNNING":
      return "success"
    case "PENDING":
      return "warning"
    case "TERMINATED":
      return "info"
    case "ERROR":
      return "destructive"
  }
}

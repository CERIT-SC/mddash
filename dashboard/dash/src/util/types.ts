
export interface Experiment {
    id: string
    name: string
    source_message: string
    status: string
    step: number
    token: string
    tuner_jobs: { [key: string]: TunerStatus }
    gromacs_jobs: { [key: string]: any }
    mdrepo_id: string | null
}


export interface TunerStatus {
    tuner_run_id: string
    cluster_resources: string
    summary: {
        RUNNING: number
        PENDING: number
        TERMINATED: number
        ERROR: number
    }
    trials: TunerTrial[]
}

export interface TunerTrial {
    id: string
    status: "RUNNING" | "PENDING" | "TERMINATED" | "ERROR"
    performance: number | null
    pme: string
    nb: string
    np: number
    ntomp: number
}

// NOTE: work in progress
export interface GromacsJob {
    id: string
    status: "RUNNING" | "PENDING" | "TERMINATED" | "ERROR"
    pme: string
    np: number
    ntomp: number
    nb: string
}

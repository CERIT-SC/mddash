export interface Experiment {
    id: string;
    name: string;
    source_message: string;
    status: string;
    step: number;
    token: string;
    tuner_jobs: { [key: string]: TunerStatus };
    gromacs_jobs: { [key: string]: any };
    mdrepo_id: string | null;
}

export interface ResourceUsage {
    cpu: number;
    memory: number;
    gpu: number;
}

export interface FileOption {
    name: string;
    url: string;
    size: number;
}

export type PodStatus = "RUNNING" | "PENDING" | "TERMINATED" | "ERROR" | "TERMINATING" | "DOWN" | "UNKNOWN";

export interface NotebookStatus {
    status: PodStatus;
    path: string;
}

export interface TunerStatus {
    tuner_run_id: string;
    cluster_resources: string;
    summary: {
        RUNNING: number;
        PENDING: number;
        TERMINATED: number;
        ERROR: number;
    };
    trials: TunerTrial[];
}

export type JobStatus = "RUNNING" | "PENDING" | "TERMINATED" | "ERROR";

export interface TunerTrial {
    id: string;
    status: JobStatus;
    np: number;
    ntomp: number;
    pme: "cpu" | "gpu" | "auto";
    nb: "cpu" | "gpu" | "auto";
    performance: number | null;
}

// NOTE: work in progress (could extend TunerTrial)
export interface GromacsJob {
    id: string;
    status: JobStatus;
    np: number;
    ntomp: number;
    pme: "cpu" | "gpu" | "auto";
    nb: "cpu" | "gpu" | "auto";
    extra_args: string;
    performance: number | null;
}

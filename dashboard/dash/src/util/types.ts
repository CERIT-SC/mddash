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

export interface NotebookStatus {
    up: boolean;
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

export interface TunerTrial {
    id: string;
    status: "RUNNING" | "PENDING" | "TERMINATED" | "ERROR";
    np: number;
    ntomp: number;
    pme: "cpu" | "gpu" | "auto";
    nb: "cpu" | "gpu" | "auto";
    performance: number | null;
}

// NOTE: work in progress (could extend TunerTrial)
export interface GromacsJob {
    id: string;
    status: "RUNNING" | "PENDING" | "TERMINATED" | "ERROR";
    np: number;
    ntomp: number;
    pme: "cpu" | "gpu" | "auto";
    nb: "cpu" | "gpu" | "auto";
    extra_args: string;
    performance: number | null;
}

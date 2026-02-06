export interface Experiment {
    id: string;
    created_at: string;
    updated_at: string;
    name: string;
    source_message: string | null;
    notebooks_repo: string | null;
    mdrepo_id: string | null;
    mdrepo_record_url: string | null;
    step: number;
    status: string;
    notebook: Notebook;
    tuner_jobs: TunerJob[];
    gromacs_jobs: GromacsJob[];
}

export interface Notebook {
    id: number;
    experiment_id: string;
    token: string;
    path: string;
    status: PodStatus;
}

export interface TunerJob {
    id: number;
    tuner_run_id: string | null;
    experiment_id: string;
    tpr_name: string;
    tuner_status: JobStatus | null;
    error_message: string | null;
    created_at: string;
    is_stopped: boolean;
    summary: {
        RUNNING?: number;
        PENDING?: number;
        TERMINATED?: number;
        ERROR?: number;
    };
    trials: TunerTrial[];
    cluster_resources: string;
}

export interface TunerTrial {
    id: string;
    status: JobStatus;
    np: number;
    ntomp: number;
    pme: DeviceType;
    nb: DeviceType;
    performance: number | null;
}

export type DeviceType = "auto" | "cpu" | "gpu";

export interface GromacsJob {
    id: number;
    experiment_id: string;
    created_at: string;
    tpr_name: string;
    job_name: string;
    pme: DeviceType;
    nb: DeviceType;
    np: number;
    ntomp: number;
    extra_args: string;
    status: JobStatus;
    start_timestamp: number | null;
    finish_timestamp: number | null;
    nsteps: number | null;
    performance: number | null;
    nsteps_done: number | null;
    estimated_time: number | null;
}

export interface ResourceUsage {
    requests: {
        cpu: number;
        memory: number;
        storage: number;
    };
    limits: {
        cpu: number;
        memory: number;
        storage: number;
    };
}

export interface FileOption {
    name: string;
    url: string;
    size: number;
}

export type MuiColor = "primary" | "secondary" | "success" | "warning" | "error" | "info";

export type PodStatus = "RUNNING" | "PENDING" | "TERMINATED" | "ERROR" | "TERMINATING" | "DOWN" | "UNKNOWN";

export function getPodStatusColor(status: PodStatus): MuiColor {
    switch (status) {
        case "RUNNING":
            return "success";
        case "PENDING":
            return "warning";
        case "TERMINATED":
            return "info";
        case "ERROR":
            return "error";
        case "TERMINATING":
            return "warning";
        case "DOWN":
            return "error";
        case "UNKNOWN":
            return "secondary";
    }
}

export type JobStatus = "UNKNOWN" | "PENDING" | "RUNNING" | "TERMINATED" | "ERROR";

export function getJobStatusColor(status: JobStatus): MuiColor {
    switch (status) {
        case "UNKNOWN":
            return "secondary";
        case "RUNNING":
            return "success";
        case "PENDING":
            return "warning";
        case "TERMINATED":
            return "info";
        case "ERROR":
            return "error";
    }
}

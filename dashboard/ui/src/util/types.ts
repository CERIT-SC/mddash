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
    id: string;
    experiment_id: string;
    tpr_name: string;
    tuner_status: JobStatus | null;
    error_message: string | null;
    created_at: string;
    is_stopped: boolean;
    trials: TunerTrial[];
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
        storage: number | null;
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

export type StatusVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info";

export function statusBadgeClass(variant: StatusVariant): string {
    switch (variant) {
        case "success":
            return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
        case "warning":
            return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
        case "info":
            return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
        case "destructive":
            return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
        case "secondary":
            return "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200";
        default:
            return "";
    }
}

export type PodStatus =
    | "RUNNING"
    | "PENDING"
    | "INITIALIZING"
    | "TERMINATED"
    | "ERROR"
    | "TERMINATING"
    | "DOWN"
    | "UNKNOWN";

export function getPodStatusVariant(status: PodStatus): StatusVariant {
    switch (status) {
        case "RUNNING":
            return "success";
        case "PENDING":
        case "INITIALIZING":
        case "TERMINATING":
            return "warning";
        case "TERMINATED":
            return "info";
        case "ERROR":
        case "DOWN":
            return "destructive";
        case "UNKNOWN":
            return "secondary";
    }
}

export type JobStatus = "UNKNOWN" | "PENDING" | "RUNNING" | "TERMINATED" | "ERROR";

export function getJobStatusVariant(status: JobStatus): StatusVariant {
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
            return "destructive";
    }
}

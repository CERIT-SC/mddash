export interface Experiment {
    id: string;
    name: string;
    source_message: string;
    status: string;
    step: number;
    token: string;
    notebook_status: PodStatus;
    tuner_jobs: { [key: string]: TunerStatus };
    gromacs_jobs: { [key: string]: GromacsJob };
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

export type MuiColor = "primary" | "secondary" | "success" | "warning" | "error" | "info";

export type PodStatus = "RUNNING" | "PENDING" | "TERMINATED" | "ERROR" | "TERMINATING" | "DOWN" | "UNKNOWN";

export namespace PodStatus {
    /**
     * Get the color associated with a pod status
     * @param status The pod status
     * @returns Color name suitable for Material-UI components
     */
    export function getColor(status: PodStatus): MuiColor {
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
}

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

export namespace JobStatus {
    /**
     * Get the color associated with a job status
     * @param status The job status
     * @returns Color name suitable for Material-UI components
     */
    export function getColor(status: JobStatus): MuiColor {
        switch (status) {
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
}

export type DeviceType = "cpu" | "gpu" | "auto";

export interface TunerTrial {
    id: string;
    status: JobStatus;
    np: number;
    ntomp: number;
    pme: DeviceType;
    nb: DeviceType;
    performance: number | null;
}

export interface GromacsJob {
    experiment_id: string;
    tpr_name: string;
    np: number;
    ntomp: number;
    pme: DeviceType;
    nb: DeviceType;
    extra_args: string;
    job_name: string;
    status: JobStatus;
    start_timestamp: number | null;
    estimated_time: number | null;
    nsteps: number | null;
    nsteps_done: number | null;
    performance: number | null;
}

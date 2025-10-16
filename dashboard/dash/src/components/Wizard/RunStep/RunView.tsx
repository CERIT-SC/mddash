import { useState, useEffect, useMemo, useCallback } from "react";

import {
    Box,
    Stack,
    Typography,
    CircularProgress,
    Chip,
    Button,
    FormControl,
    MenuItem,
    InputLabel,
    Select,
    LinearProgress,
} from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { GromacsJob, JobStatus } from "@/util/types";
import { formatDuration } from "@/util/helpers";
import { gmx_status, gmx_logs } from "@/util/api";
import LogsView from "@/components/LogsView";
import ConfirmDialog from "@/components/ConfirmDialog";
import StartForm from "./StartForm";

const POLLING_INTERVAL_MS = 5000;
const LOG_TAIL_LINES = 100;

type LogType = "gmx" | "stdout" | "stderr";

interface RunViewProps extends WizardStepProps {
    tprName: string;
    deleteJob: (tprName: string) => void;
}

const RunView = (props: RunViewProps) => {
    const { experiment, tprName, deleteJob, setErrorMessage } = props;

    const [loading, setLoading] = useState(false);
    const [jobRunning, setJobRunning] = useState(false);
    const [jobStatus, setJobStatus] = useState<GromacsJob | null>(null);
    const [logType, setLogType] = useState<LogType | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchStatus = useCallback(
        async (showError: boolean) => {
            const { data, error } = await gmx_status(experiment.id, tprName);
            if (showError && error) {
                setErrorMessage(error);
            }
            setJobStatus(data || null);
            setJobRunning(!!data);
        },
        [experiment.id, tprName, setErrorMessage]
    );

    useEffect(() => {
        setLoading(true);
        setLogType(null);
        fetchStatus(false).finally(() => setLoading(false));
    }, [fetchStatus]);

    useEffect(() => {
        const isJobActive = jobStatus?.status === "PENDING" || jobStatus?.status === "RUNNING";

        if (!isJobActive) {
            return;
        }

        const intervalId = window.setInterval(() => {
            fetchStatus(true);
        }, POLLING_INTERVAL_MS);

        return () => {
            clearInterval(intervalId);
        };
    }, [jobStatus?.status, fetchStatus]);

    const getLogs = useCallback(async () => {
        if (!logType) {
            return "No log type selected";
        }

        const { data, error } = await gmx_logs(experiment.id, tprName, logType, LOG_TAIL_LINES);
        if (error) {
            setErrorMessage(error);
        }
        return data || "";
    }, [experiment.id, tprName, logType, setErrorMessage]);

    const statusDisplay = useMemo(() => {
        if (!jobStatus) {
            return null;
        }

        const isRunningWithProgress =
            jobStatus.status === "RUNNING" && jobStatus.nsteps !== null && jobStatus.nsteps_done !== null;

        const progressPercentage = isRunningWithProgress ? (jobStatus.nsteps_done! / jobStatus.nsteps!) * 100 : 0;

        return (
            <Stack spacing={2} alignItems="flex-start">
                <Typography variant="subtitle1" color="text.secondary">
                    Status
                </Typography>
                <Chip label={jobStatus.status} color={JobStatus.getColor(jobStatus.status)} />

                {isRunningWithProgress && (
                    <>
                        <Typography variant="subtitle1" color="text.secondary">
                            Progress
                        </Typography>
                        <Box sx={{ width: "100%", minWidth: 300 }}>
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                                <Box sx={{ width: "100%", mr: 1 }}>
                                    <LinearProgress variant="determinate" value={progressPercentage} />
                                </Box>
                                <Box sx={{ minWidth: 35 }}>
                                    <Typography variant="body2" color="text.secondary">
                                        {`${progressPercentage.toFixed(1)}%`}
                                    </Typography>
                                </Box>
                            </Box>
                            <Typography variant="body2" color="text.secondary">
                                {`${jobStatus.nsteps_done!.toLocaleString()} / ${jobStatus.nsteps!.toLocaleString()} steps`}
                            </Typography>
                            {jobStatus.estimated_time !== null && (
                                <Typography variant="body2" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                                    Estimated time remaining: {formatDuration(jobStatus.estimated_time)}
                                </Typography>
                            )}
                        </Box>
                    </>
                )}

                {jobStatus.performance && (
                    <>
                        <Typography variant="subtitle1" color="text.secondary">
                            Performance
                        </Typography>
                        <Typography variant="body1">{`${jobStatus.performance.toFixed(2)} ns/day`}</Typography>
                    </>
                )}

                <Typography variant="subtitle1" color="text.secondary">
                    Processes
                </Typography>
                <Typography variant="body1">
                    {jobStatus.np} × {jobStatus.ntomp} threads
                </Typography>

                <Typography variant="subtitle1" color="text.secondary">
                    PME / NB
                </Typography>
                <Typography variant="body1">
                    {jobStatus.pme} / {jobStatus.nb}
                </Typography>

                {jobStatus.extra_args && (
                    <>
                        <Typography variant="subtitle1" color="text.secondary">
                            Extra Arguments
                        </Typography>
                        <Typography variant="body1">{jobStatus.extra_args}</Typography>
                    </>
                )}
            </Stack>
        );
    }, [jobStatus]);

    const handleLogTypeChange = useCallback((value: string) => {
        setLogType((value as LogType) || null);
    }, []);

    const handleDeleteClick = useCallback(() => {
        setConfirmDeleteDialog(true);
    }, []);

    const handleConfirmDelete = useCallback(() => {
        deleteJob(tprName);
    }, [deleteJob, tprName]);

    const logsAvailable = jobStatus?.nsteps !== null;
    const shouldRefreshLogs = jobStatus?.status === "RUNNING";

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                <CircularProgress />
            </Box>
        );
    }

    return (
        <>
            <Box sx={{ mt: 2 }}>
                {jobRunning ? (
                    <Stack spacing={2} alignItems="flex-start">
                        {statusDisplay}

                        <Button variant="contained" color="error" onClick={handleDeleteClick}>
                            Delete Job
                        </Button>

                        {logsAvailable && (
                            <>
                                <Typography variant="subtitle1" color="text.secondary">
                                    Logs
                                </Typography>

                                <FormControl sx={{ minWidth: 200 }}>
                                    <InputLabel id="log-type-selector">Log Type</InputLabel>
                                    <Select
                                        labelId="log-type-selector"
                                        label="Log Type"
                                        value={logType || ""}
                                        onChange={(e) => handleLogTypeChange(e.target.value)}
                                    >
                                        <MenuItem value="">
                                            <em>None</em>
                                        </MenuItem>
                                        <MenuItem value="gmx">Gromacs Log</MenuItem>
                                        <MenuItem value="stdout">Standard Output</MenuItem>
                                        <MenuItem value="stderr">Standard Error</MenuItem>
                                    </Select>
                                </FormControl>

                                {logType && (
                                    <LogsView
                                        getLogs={getLogs}
                                        refreshInterval={shouldRefreshLogs ? POLLING_INTERVAL_MS : undefined}
                                    />
                                )}
                            </>
                        )}
                    </Stack>
                ) : (
                    <StartForm fetchStatus={fetchStatus} {...props} />
                )}
            </Box>
            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={handleConfirmDelete}
                message="Are you sure you want to delete this Gromacs job? The data will be lost."
            />
        </>
    );
};

export default RunView;

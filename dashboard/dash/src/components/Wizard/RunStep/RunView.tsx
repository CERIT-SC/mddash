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

interface RunViewProps extends WizardStepProps {
    tprName: string;
    deleteJob: (tprName: string) => void;
}

const RunView = (props: RunViewProps) => {
    const { experiment, tprName, deleteJob, setErrorMessage } = props;

    const [loading, setLoading] = useState(false);
    const [jobRunning, setJobRunning] = useState(false);
    const [jobStatus, setJobStatus] = useState<GromacsJob | null>(null);
    const [logType, setLogType] = useState<"gmx" | "stdout" | "stderr" | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchStatus = async (showError: boolean) => {
        const { data, error } = await gmx_status(experiment.id, tprName);
        if (showError && error) setErrorMessage(error);
        setJobStatus(data || null);
        setJobRunning(!!data);
    };

    // initial fetch
    useEffect(() => {
        setLoading(true);
        setLogType(null);
        fetchStatus(false).finally(() => setLoading(false));
    }, [tprName, experiment.id]);

    // polling for job status
    useEffect(() => {
        let intervalId: number | null = null;

        if (jobStatus?.status === "PENDING" || jobStatus?.status === "RUNNING") {
            intervalId = window.setInterval(() => {
                fetchStatus(true);
            }, 5000);
        }

        return () => {
            if (intervalId !== null) {
                clearInterval(intervalId);
            }
        };
    }, [jobStatus?.status]);

    const getLogs = useCallback(async () => {
        if (!logType) return "No log type selected";

        const { data, error } = await gmx_logs(experiment.id, tprName, logType, 100);
        setErrorMessage(error || "");
        return data || "";
    }, [experiment.id, tprName, logType, setErrorMessage]);

    const statusDisplay = useMemo(() => {
        if (!jobStatus) return null;

        return (
            <Stack spacing={2} alignItems="flex-start">
                <Typography variant="subtitle1" color="text.secondary">
                    Status
                </Typography>
                <Chip label={jobStatus.status} color={JobStatus.getColor(jobStatus.status)} />

                {jobStatus.status === "RUNNING" && jobStatus.nsteps !== null && jobStatus.nsteps_done !== null && (
                    <>
                        <Typography variant="subtitle1" color="text.secondary">
                            Progress
                        </Typography>
                        <Box sx={{ width: "100%", minWidth: 300 }}>
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                                <Box sx={{ width: "100%", mr: 1 }}>
                                    <LinearProgress
                                        variant="determinate"
                                        value={(jobStatus.nsteps_done / jobStatus.nsteps) * 100}
                                    />
                                </Box>
                                <Box sx={{ minWidth: 35 }}>
                                    <Typography variant="body2" color="text.secondary">
                                        {`${((jobStatus.nsteps_done / jobStatus.nsteps) * 100).toFixed(1)}%`}
                                    </Typography>
                                </Box>
                            </Box>
                            <Typography variant="body2" color="text.secondary">
                                {`${jobStatus.nsteps_done.toLocaleString()} / ${jobStatus.nsteps.toLocaleString()} steps`}
                            </Typography>
                            {jobStatus.estimated_time != null && (
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
    }, [
        jobStatus?.status,
        jobStatus?.np,
        jobStatus?.ntomp,
        jobStatus?.pme,
        jobStatus?.nb,
        jobStatus?.extra_args,
        jobStatus?.nsteps,
        jobStatus?.nsteps_done,
        jobStatus?.estimated_time,
        jobStatus?.performance,
    ]);

    return (
        <>
            {(loading && (
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                    <CircularProgress />
                </Box>
            )) || (
                <Box sx={{ mt: 2 }}>
                    {jobRunning ? (
                        <Stack spacing={2} alignItems="flex-start">
                            {statusDisplay}

                            <Button
                                variant="contained"
                                color="error"
                                onClick={() => {
                                    setConfirmDeleteDialog(true);
                                }}
                            >
                                Delete Job
                            </Button>

                            {jobStatus?.status !== "PENDING" && (
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
                                            onChange={(e) =>
                                                setLogType(
                                                    (e.target.value as "gmx" | "stdout" | "stderr" | null) || null
                                                )
                                            }
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
                                            refreshInterval={jobStatus?.status == "RUNNING" ? 5000 : undefined}
                                        />
                                    )}
                                </>
                            )}
                        </Stack>
                    ) : (
                        <StartForm fetchStatus={fetchStatus} {...props} />
                    )}
                </Box>
            )}
            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(tprName)}
                message="Are you sure you want to delete this Gromacs job? The data will be lost."
            />
        </>
    );
};

export default RunView;

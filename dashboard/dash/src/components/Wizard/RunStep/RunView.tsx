import { useState, useEffect, useCallback } from "react";

import {
    Box,
    Stack,
    Typography,
    CircularProgress,
    FormControl,
    MenuItem,
    InputLabel,
    Select,
    Paper,
    SelectChangeEvent,
} from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { GromacsJob } from "@/util/types";
import { gmx_status, gmx_logs } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";
import LogsView from "@/components/LogsView";
import StartForm from "./StartForm";
import JobStatusDisplay from "./JobStatusDisplay";

const POLLING_INTERVAL_MS = 5000;
const LOG_TAIL_LINES = 100;

type LogType = "gmx" | "stdout" | "stderr" | "";

interface RunViewProps extends WizardStepProps {
    tprName: string;
    onStartJob: () => void;
}

const RunView = (props: RunViewProps) => {
    const { experiment, tprName, onStartJob } = props;
    const { showError } = useNotification();

    const [loading, setLoading] = useState(false);
    const [jobStatus, setJobStatus] = useState<GromacsJob | null>(null);
    const [logType, setLogType] = useState<LogType>("");

    const fetchStatus = useCallback(
        async (displayError: boolean) => {
            const { data, error } = await gmx_status(experiment.id, tprName);
            if (displayError && error) {
                showError(error);
            }
            setJobStatus(data || null);
        },
        [experiment.id, tprName, showError]
    );

    useEffect(() => {
        setLoading(true);
        setLogType("");
        fetchStatus(false).finally(() => setLoading(false));
    }, [fetchStatus]);

    useEffect(() => {
        if (jobStatus?.status !== "PENDING" && jobStatus?.status !== "RUNNING") {
            return;
        }

        const intervalId = setInterval(() => fetchStatus(true), POLLING_INTERVAL_MS);
        return () => clearInterval(intervalId);
    }, [jobStatus?.status, fetchStatus]);

    const handleJobStarted = () => {
        fetchStatus(true);
        onStartJob();
    };

    const getLogs = useCallback(async () => {
        if (!logType) return "No log type selected";

        const { data, error } = await gmx_logs(experiment.id, tprName, logType, LOG_TAIL_LINES);
        if (error) showError(error);
        return data || "";
    }, [experiment.id, tprName, logType, showError]);

    const handleLogTypeChange = (event: SelectChangeEvent<string>) => {
        setLogType(event.target.value as LogType);
    };

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                <CircularProgress />
            </Box>
        );
    }

    if (!jobStatus) {
        return <StartForm {...props} onStartJob={handleJobStarted} />;
    }

    const logsAvailable = jobStatus.nsteps !== null;
    const shouldRefreshLogs = jobStatus.status === "RUNNING";

    return (
        <Stack spacing={2} alignItems="flex-start">
            <JobStatusDisplay jobStatus={jobStatus} />

            {logsAvailable && (
                <>
                    <Typography variant="subtitle1">Logs</Typography>
                    <Paper variant="outlined" sx={{ padding: 2, width: "100%" }}>
                        <Stack direction="row">
                            <Typography variant="body1" sx={{ alignSelf: "center", mr: 2 }}>
                                Select:
                            </Typography>

                            <FormControl sx={{ minWidth: 200 }}>
                                <InputLabel id="log-type-selector">Log Type</InputLabel>
                                <Select
                                    labelId="log-type-selector"
                                    label="Log Type"
                                    value={logType}
                                    onChange={handleLogTypeChange}
                                >
                                    <MenuItem value="">
                                        <em>None</em>
                                    </MenuItem>
                                    <MenuItem value="gmx">Gromacs Log</MenuItem>
                                    <MenuItem value="stdout">Standard Output</MenuItem>
                                    <MenuItem value="stderr">Standard Error</MenuItem>
                                </Select>
                            </FormControl>
                        </Stack>

                        {logType && (
                            <LogsView
                                getLogs={getLogs}
                                refreshInterval={shouldRefreshLogs ? POLLING_INTERVAL_MS : undefined}
                                sx={{ mt: 2 }}
                            />
                        )}
                    </Paper>
                </>
            )}
        </Stack>
    );
};

export default RunView;

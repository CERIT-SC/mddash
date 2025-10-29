import { useEffect, useState } from "react";

import { Box, Stack, Button, Typography, CircularProgress, TextField, Alert } from "@mui/material";
import { Delete, PlayArrow, Cancel, Pause } from "@mui/icons-material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { tuner_status, run_tuner } from "@/util/api";
import { TunerJob, TunerTrial } from "@/util/types";
import { useNotification } from "@/contexts/NotificationContext";
import { StartForm } from "@/components/Wizard/RunStep";
import ConfirmDialog from "@/components/ConfirmDialog";
import TunerTable from "./TunerTable";

interface TunerViewProps extends WizardStepProps {
    tprName: string;
    cancelJob: (tprName: string) => void;
    stopJob: (tprName: string) => void;
    deleteJob: (tprName: string) => void;
}

const TunerView = (props: TunerViewProps) => {
    const { experiment, tprName, stopJob, deleteJob, cancelJob, nextStep, changeStep } = props;
    const { showError } = useNotification();

    const [loading, setLoading] = useState(false);
    const [tunerStarted, setTunerStarted] = useState(false);
    const [tunerStopped, setTunerStopped] = useState(false);
    const [tuner, setTuner] = useState<TunerJob | null>(null);
    const [selectedTrial, setSelectedTrial] = useState<TunerTrial | null>(null);
    const [nsteps, setNsteps] = useState<number | "">(25000);

    const [confirmStopDialog, setConfirmStopDialog] = useState(false);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchStatus = async (displayError: boolean) => {
        const { data, error } = await tuner_status(experiment.id, tprName);
        if (displayError && error) showError(error);
        setTuner(data || null);
        setTunerStarted(!!data && !data.is_pending && !!data.trials && data.trials.length > 0);
        setTunerStopped(data?.is_stopped || false);

        // Maintain selected trial after data refresh
        if (selectedTrial && data?.trials) {
            const updatedSelectedTrial = data.trials.find((trial) => trial.id === selectedTrial.id);
            if (updatedSelectedTrial) {
                setSelectedTrial(updatedSelectedTrial);
            } else {
                // Trial no longer exists, clear selection
                setSelectedTrial(null);
            }
        }
    };

    const runTuner = async () => {
        const actualNsteps = nsteps === "" ? 25000 : nsteps;
        const { error } = await run_tuner(experiment.id, tprName, actualNsteps);
        if (error) showError(error);
        fetchStatus(true);
    };

    const goToRunStep = async (_: boolean) => {
        if (experiment.step < 2) nextStep();
        else changeStep(2);
    };

    // initial fetch
    useEffect(() => {
        setLoading(true);
        fetchStatus(false).finally(() => setLoading(false));
    }, [tprName, experiment.id]);

    // polling for tuner status
    useEffect(() => {
        let intervalId: number | null = null;

        // refresh tuner status every 5 seconds
        const shouldPoll =
            tuner?.is_pending || (tunerStarted && !tunerStopped) || (tuner?.tuner_run_id && !tunerStarted);

        if (shouldPoll) {
            intervalId = window.setInterval(() => {
                fetchStatus(true);
            }, 5000);
        }

        return () => {
            if (intervalId !== null) {
                window.clearInterval(intervalId);
            }
        };
    }, [tuner?.is_pending, tuner?.tuner_run_id, tunerStarted, tunerStopped]);

    return (
        <>
            {(loading && (
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                    <CircularProgress />
                </Box>
            )) || (
                <>
                    {(tunerStarted && (
                        <Stack direction="column" spacing={2}>
                            <TunerTable
                                rows={tuner?.trials || []}
                                selectedTrial={selectedTrial}
                                setSelectedTrial={setSelectedTrial}
                            />

                            <Stack direction="row" spacing={2} justifyContent="flex-end">
                                {tunerStopped || (
                                    <Button
                                        variant="contained"
                                        color="warning"
                                        startIcon={<Pause />}
                                        onClick={() => setConfirmStopDialog(true)}
                                    >
                                        Stop
                                    </Button>
                                )}
                                <Button
                                    variant="contained"
                                    color="error"
                                    startIcon={<Delete />}
                                    onClick={() => setConfirmDeleteDialog(true)}
                                >
                                    Delete
                                </Button>
                            </Stack>

                            {selectedTrial && (
                                <StartForm
                                    fetchStatus={goToRunStep}
                                    np={selectedTrial.np}
                                    ntomp={selectedTrial.ntomp}
                                    nb={selectedTrial.nb}
                                    pme={selectedTrial.pme}
                                    {...props}
                                />
                            )}
                        </Stack>
                    )) || (
                        <Stack direction="column" spacing={2} alignItems="center">
                            {tuner?.error_message && (
                                <Alert severity="error" sx={{ width: "100%" }}>
                                    <strong>Error:</strong> {tuner.error_message}
                                </Alert>
                            )}
                            {tuner?.is_pending && (
                                <Alert severity="info" sx={{ width: "100%" }}>
                                    Preparing tuner job (modifying TPR file)...
                                </Alert>
                            )}
                            {!tuner?.is_pending && !tuner?.error_message && (
                                <Typography variant="h4">Tuner not running.</Typography>
                            )}

                            {/* Show input and start button only when no job exists or job has error */}
                            {(!tuner || tuner.error_message) && (
                                <>
                                    <TextField
                                        label="Number of steps (nsteps)"
                                        type="number"
                                        value={nsteps}
                                        onChange={(e) => {
                                            const val = e.target.value;
                                            if (val === "") {
                                                setNsteps("");
                                            } else {
                                                const num = parseInt(val);
                                                if (!isNaN(num)) {
                                                    setNsteps(num);
                                                }
                                            }
                                        }}
                                        sx={{ width: 300 }}
                                        disabled={!!tuner?.error_message}
                                    />
                                    <Button
                                        variant="contained"
                                        color="primary"
                                        startIcon={<PlayArrow />}
                                        onClick={runTuner}
                                        sx={{ width: 200 }}
                                    >
                                        Start tune job
                                    </Button>
                                </>
                            )}

                            {/* Show appropriate button based on state */}
                            {tuner?.is_pending ? (
                                <Button
                                    variant="contained"
                                    color="error"
                                    startIcon={<Delete />}
                                    onClick={() => setConfirmDeleteDialog(true)}
                                    sx={{ width: 200 }}
                                >
                                    Delete
                                </Button>
                            ) : tuner?.error_message ? (
                                <Button
                                    variant="contained"
                                    color="error"
                                    startIcon={<Delete />}
                                    onClick={() => setConfirmDeleteDialog(true)}
                                    sx={{ width: 200 }}
                                >
                                    Delete
                                </Button>
                            ) : (
                                !tuner && (
                                    <Button
                                        variant="contained"
                                        color="error"
                                        startIcon={<Cancel />}
                                        onClick={() => cancelJob(tprName)}
                                        sx={{ width: 200 }}
                                    >
                                        Cancel
                                    </Button>
                                )
                            )}
                        </Stack>
                    )}
                </>
            )}

            <ConfirmDialog
                open={confirmStopDialog}
                setOpen={setConfirmStopDialog}
                confirmColor="warning"
                onConfirm={() => stopJob(tprName)}
                message="Are you sure you want to stop the tuning job? You cannot resume it, but data will be preserved."
            />
            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(tprName)}
                message={
                    tuner?.is_pending
                        ? "Are you sure you want to delete this tuning job? The TPR modification will be cancelled."
                        : "Are you sure you want to delete this tuning job? The data will be lost."
                }
            />
        </>
    );
};

export default TunerView;

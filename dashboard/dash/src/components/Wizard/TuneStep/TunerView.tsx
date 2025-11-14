import { useEffect, useState, useCallback } from "react";

import { Box, Stack, Button, Typography, CircularProgress, TextField, Alert } from "@mui/material";
import { PlayArrow, Pause } from "@mui/icons-material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { tuner_status, run_tuner } from "@/util/api";
import { TunerJob, TunerTrial } from "@/util/types";
import { useNotification } from "@/contexts/NotificationContext";
import { StartForm } from "@/components/Wizard/RunStep";
import ConfirmDialog from "@/components/ConfirmDialog";
import TunerTable from "./TunerTable";

const DEFAULT_NSTEPS = 25000;
const POLLING_INTERVAL = 5000;

interface TunerViewProps extends WizardStepProps {
    tprName: string;
    stopJob: (tprName: string) => void;
    onStartTuner?: (tprName: string) => void;
}

const TunerView = (props: TunerViewProps) => {
    const { experiment, tprName, stopJob, nextStep, changeStep, onStartTuner } = props;
    const { showError } = useNotification();

    const [loading, setLoading] = useState(false);
    const [tuner, setTuner] = useState<TunerJob | null>(null);
    const [selectedTrial, setSelectedTrial] = useState<TunerTrial | null>(null);
    const [nsteps, setNsteps] = useState<number | "">(DEFAULT_NSTEPS);
    const [confirmStopDialog, setConfirmStopDialog] = useState(false);

    const tunerStarted = !!tuner && !tuner.is_pending && !!tuner.trials && tuner.trials.length > 0;
    const tunerStopped = tuner?.is_stopped || false;

    const fetchStatus = useCallback(
        async (displayError: boolean) => {
            const { data, error } = await tuner_status(experiment.id, tprName);
            if (displayError && error) showError(error);
            setTuner(data || null);

            if (selectedTrial && data?.trials) {
                const updatedTrial = data.trials.find((trial) => trial.id === selectedTrial.id);
                setSelectedTrial(updatedTrial || null);
            }
        },
        [experiment.id, tprName, selectedTrial, showError]
    );

    const runTuner = useCallback(async () => {
        const actualNsteps = nsteps === "" ? DEFAULT_NSTEPS : nsteps;
        const { error } = await run_tuner(experiment.id, tprName, actualNsteps);
        if (error) showError(error);
        onStartTuner?.(tprName);
        fetchStatus(true);
    }, [nsteps, experiment.id, tprName, showError, onStartTuner, fetchStatus]);

    const goToRunStep = useCallback(async () => {
        experiment.step < 2 ? nextStep() : changeStep(2);
    }, [experiment.step, nextStep, changeStep]);

    // initial fetch
    useEffect(() => {
        setLoading(true);
        fetchStatus(false).finally(() => setLoading(false));
    }, [tprName, experiment.id]);

    useEffect(() => {
        const shouldPoll =
            tuner?.is_pending || (tunerStarted && !tunerStopped) || (tuner?.tuner_run_id && !tunerStarted);

        if (!shouldPoll) return;

        const intervalId = window.setInterval(() => fetchStatus(true), POLLING_INTERVAL);
        return () => window.clearInterval(intervalId);
    }, [tuner?.is_pending, tuner?.tuner_run_id, tunerStarted, tunerStopped, fetchStatus]);

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                <CircularProgress />
            </Box>
        );
    }

    return (
        <>
            {tunerStarted ? (
                <Stack direction="column" spacing={2}>
                    <TunerTable
                        rows={tuner?.trials || []}
                        selectedTrial={selectedTrial}
                        setSelectedTrial={setSelectedTrial}
                    />

                    {!tunerStopped && (
                        <Stack direction="row" spacing={2} justifyContent="flex-end">
                            <Button
                                variant="contained"
                                color="warning"
                                startIcon={<Pause />}
                                onClick={() => setConfirmStopDialog(true)}
                            >
                                Stop
                            </Button>
                        </Stack>
                    )}

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
            ) : (
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
                        <Typography variant="h3">Configure tuning job for {tprName}</Typography>
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
                                    setNsteps(val === "" ? "" : parseInt(val) || "");
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
                </Stack>
            )}

            <ConfirmDialog
                open={confirmStopDialog}
                setOpen={setConfirmStopDialog}
                confirmColor="warning"
                onConfirm={() => stopJob(tprName)}
                message="Are you sure you want to stop the tuning job? You cannot resume it, but data will be preserved."
            />
        </>
    );
};

export default TunerView;

import { useEffect, useState, useCallback } from "react";

import { Box, Stack, Button } from "@mui/material";
import { SkipNext } from "@mui/icons-material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { tuner_statuses, stop_tuner, delete_tuner } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import ConfirmDialog from "@/components/ConfirmDialog";
import TunerView from "./TunerView";
import TprSelector from "@/components/Wizard/TprSelector";

const TuneStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);
    const [existingJobs, setExistingJobs] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [deleteTpr, setDeleteTpr] = useState<string | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);
    const [skipDialog, setSkipDialog] = useState(false);

    const fetchTunerJobs = useCallback(async () => {
        setLoading(true);
        const { data, error } = await tuner_statuses(experiment.id);
        if (error) showError(error);
        const jobs = data || [];

        if (jobs.length === 0) setSelectedTpr(null);

        const jobNames = jobs.map((job) => job.tpr_name);
        setTprFiles(jobNames);
        setExistingJobs(jobNames);
        setLoading(false);
    }, [experiment.id, showError]);

    const handleAddTpr = useCallback((tpr: string) => {
        setTprFiles((prev) => [...prev, tpr]);
        setSelectedTpr(tpr);
    }, []);

    const handleDeleteTpr = useCallback(
        (tpr: string) => {
            if (existingJobs.includes(tpr)) {
                setDeleteTpr(tpr);
                setConfirmDeleteDialog(true);
            } else {
                setSelectedTpr(null);
                setTprFiles((prev) => prev.filter((t) => t !== tpr));
            }
        },
        [existingJobs],
    );

    const stopJob = useCallback(
        async (tprName: string) => {
            const { error } = await stop_tuner(experiment.id, tprName);
            if (error) showError(error);
            fetchTunerJobs();
        },
        [experiment.id, showError, fetchTunerJobs],
    );

    const deleteJob = useCallback(
        async (tprName: string) => {
            const { error } = await delete_tuner(experiment.id, tprName);
            if (error) showError(error);
            setSelectedTpr(null);
            fetchTunerJobs();
        },
        [experiment.id, showError, fetchTunerJobs],
    );

    useEffect(() => {
        fetchTunerJobs();
    }, [fetchTunerJobs]);

    return (
        <Stack direction="column" alignItems="center" width="100%">
            <Stack direction="row" spacing={2} width="90%">
                <TprSelector
                    experimentId={experiment.id}
                    title="Tuner Jobs"
                    addTitle="Add Tuner Job"
                    tprFiles={tprFiles}
                    selectedTpr={selectedTpr}
                    loading={loading}
                    onAddTpr={handleAddTpr}
                    onDeleteTpr={handleDeleteTpr}
                    onSelectTpr={setSelectedTpr}
                />

                {selectedTpr ? (
                    <Box flex={1}>
                        <TunerView tprName={selectedTpr} stopJob={stopJob} onStartTuner={fetchTunerJobs} {...props} />
                    </Box>
                ) : (
                    <Box flex={1} display="flex" justifyContent="flex-end" alignItems="flex-start">
                        <Button
                            variant="outlined"
                            color="error"
                            startIcon={<SkipNext />}
                            onClick={() => setSkipDialog(true)}
                        >
                            Skip Tuning
                        </Button>
                    </Box>
                )}
            </Stack>

            <ConfirmDialog
                open={skipDialog}
                setOpen={setSkipDialog}
                title="Skip Tuning?"
                message="Are you sure you want to skip tuning? Your simulation may run slowly without tuning."
                onConfirm={props.nextStep}
            />

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(deleteTpr!)}
                message={"Are you sure you want to delete this tuning job? The data will be lost."}
            />
        </Stack>
    );
};

export default TuneStep;

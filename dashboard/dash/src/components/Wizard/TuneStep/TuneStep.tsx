import { useEffect, useState, useCallback } from "react";

import { Box, Stack } from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { tuner_statuses, stop_tuner, delete_tuner } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";
import ConfirmDialog from "@/components/ConfirmDialog";
import TunerView from "./TunerView";
import TprSelector from "@/components/Wizard/TprSelector";

const TuneStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);
    const [successfulJobs, setSuccessfulJobList] = useState<string[]>([]);
    const [deleteTpr, setDeleteTpr] = useState<string | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchTunerJobs = useCallback(async () => {
        const { data, error } = await tuner_statuses(experiment.id);
        if (error) showError(error);
        const jobs = data || [];

        if (jobs.length === 0) setSelectedTpr(null);

        setTprFiles(jobs.map((job) => job.tpr_name));
        setSuccessfulJobList(jobs.filter((job) => !job.error_message).map((job) => job.tpr_name));
    }, [experiment.id, showError]);

    const handleAddTpr = useCallback((tpr: string) => {
        setTprFiles((prev) => [...prev, tpr]);
        setSelectedTpr(tpr);
    }, []);

    const handleDeleteTpr = useCallback(
        (tpr: string) => {
            if (successfulJobs.includes(tpr)) {
                setDeleteTpr(tpr);
                setConfirmDeleteDialog(true);
            } else {
                setSelectedTpr(null);
                setTprFiles((prev) => prev.filter((t) => t !== tpr));
            }
        },
        [successfulJobs]
    );

    const stopJob = useCallback(
        async (tprName: string) => {
            const { error } = await stop_tuner(experiment.id, tprName);
            if (error) showError(error);
            fetchTunerJobs();
        },
        [experiment.id, showError, fetchTunerJobs]
    );

    const deleteJob = useCallback(
        async (tprName: string) => {
            const { error } = await delete_tuner(experiment.id, tprName);
            if (error) showError(error);
            setSelectedTpr(null);
            fetchTunerJobs();
        },
        [experiment.id, showError, fetchTunerJobs]
    );

    useEffect(() => {
        fetchTunerJobs();
    }, [fetchTunerJobs]);

    return (
        <Stack direction="row" spacing={2}>
            <TprSelector
                experimentId={experiment.id}
                addTitle="Add Tuner Job"
                tprFiles={tprFiles}
                selectedTpr={selectedTpr}
                onAddTpr={handleAddTpr}
                onDeleteTpr={handleDeleteTpr}
                onSelectTpr={setSelectedTpr}
            />

            {selectedTpr && (
                <Box flex={1}>
                    <TunerView tprName={selectedTpr} stopJob={stopJob} onStartTuner={fetchTunerJobs} {...props} />
                </Box>
            )}

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

import { useState, useEffect, useCallback } from "react";

import { Box, Stack } from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { delete_gmx, gmx_statuses } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import ConfirmDialog from "@/components/ConfirmDialog";
import RunView from "./RunView";
import TprSelector from "../TprSelector";

const RunStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);
    const [existingJobs, setExistingJobs] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [deleteTpr, setDeleteTpr] = useState<string | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchGromacsJobs = useCallback(async () => {
        setLoading(true);
        const { data, error } = await gmx_statuses(experiment.id);
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

    const deleteJob = useCallback(
        async (tprName: string) => {
            const { error } = await delete_gmx(experiment.id, tprName);
            if (error) showError(error);
            setSelectedTpr(null);
            fetchGromacsJobs();
        },
        [experiment.id, showError, fetchGromacsJobs],
    );

    useEffect(() => {
        fetchGromacsJobs();
    }, [fetchGromacsJobs]);

    return (
        <Stack direction="column" alignItems="center" spacing={2}>
            <Stack direction="row" width="90%" spacing={2}>
                <TprSelector
                    experimentId={experiment.id}
                    title="Gromacs Jobs"
                    addTitle="Add Gromacs Job"
                    tprFiles={tprFiles}
                    selectedTpr={selectedTpr}
                    loading={loading}
                    onAddTpr={handleAddTpr}
                    onDeleteTpr={handleDeleteTpr}
                    onSelectTpr={setSelectedTpr}
                />

                {selectedTpr && (
                    <Box flex={1}>
                        <RunView tprName={selectedTpr} onStartJob={fetchGromacsJobs} {...props} />
                    </Box>
                )}

                <ConfirmDialog
                    open={confirmDeleteDialog}
                    setOpen={setConfirmDeleteDialog}
                    onConfirm={() => deleteJob(deleteTpr!)}
                    message={"Are you sure you want to delete this GROMACS job? The data will be lost."}
                />
            </Stack>
        </Stack>
    );
};

export default RunStep;

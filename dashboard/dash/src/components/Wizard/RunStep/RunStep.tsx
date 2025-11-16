import { useState, useEffect, useCallback } from "react";

import { Box, Stack } from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { delete_gmx, gmx_statuses } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";
import ConfirmDialog from "@/components/ConfirmDialog";
import RunView from "./RunView";
import TprSelector from "../TprSelector";

const RunStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);
    const [successfulJobs, setSuccessfulJobs] = useState<string[]>([]);
    const [deleteTpr, setDeleteTpr] = useState<string | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchGromacsJobs = useCallback(async () => {
        const { data, error } = await gmx_statuses(experiment.id);
        if (error) showError(error);
        const jobs = data || [];

        if (jobs.length === 0) setSelectedTpr(null);

        setTprFiles(jobs.map((job) => job.tpr_name));
        setSuccessfulJobs(jobs.filter((job) => job.status !== "ERROR").map((job) => job.tpr_name));
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

    const deleteJob = useCallback(
        async (tprName: string) => {
            const { error } = await delete_gmx(experiment.id, tprName);
            if (error) showError(error);
            setSelectedTpr(null);
            fetchGromacsJobs();
        },
        [experiment.id, showError, fetchGromacsJobs]
    );

    useEffect(() => {
        fetchGromacsJobs();
    }, [fetchGromacsJobs]);

    return (
        <Stack direction="row" spacing={2}>
            <TprSelector
                experimentId={experiment.id}
                title="Gromacs Jobs"
                addTitle="Add Gromacs Job"
                tprFiles={tprFiles}
                selectedTpr={selectedTpr}
                onAddTpr={handleAddTpr}
                onDeleteTpr={handleDeleteTpr}
                onSelectTpr={setSelectedTpr}
            />

            {selectedTpr && (
                <Box flex={1}>
                    <RunView tprName={selectedTpr} deleteJob={deleteJob} {...props} />
                </Box>
            )}

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(deleteTpr!)}
                message={"Are you sure you want to delete this GROMACS job? The data will be lost."}
            />
        </Stack>
    );
};

export default RunStep;

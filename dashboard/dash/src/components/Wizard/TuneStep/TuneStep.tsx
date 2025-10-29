import React, { useEffect, useState } from "react";

import { Box, Stack, Button, Tabs, Tab } from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { tuner_statuses, stop_tuner, delete_tuner } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";
import FileSelector from "@/components/FileSelector";
import ConfirmDialog from "@/components/ConfirmDialog";
import TunerView from "./TunerView";

const TuneStep = (props: WizardStepProps) => {
    const { experiment, nextStep, changeStep } = props;
    const { showError } = useNotification();

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);
    const [confirmSkipTuningDialog, setConfirmSkipTuningDialog] = useState(false);

    const handleChange = (_: React.SyntheticEvent, newValue: string) => {
        setSelectedTpr(newValue);
    };

    const newTpr = (newSelectedTpr: string) => {
        if (!newSelectedTpr) return;

        const tprFile = newSelectedTpr.split("/").pop() || newSelectedTpr;
        setSelectedTpr(tprFile);

        if (!tprFiles.includes(tprFile)) setTprFiles((prev) => [...prev, tprFile]);
    };

    const fetchTunerJobs = async () => {
        const { data, error } = await tuner_statuses(experiment.id);
        if (error) showError(error);
        const jobs = data || [];

        if (jobs.length === 0) setSelectedTpr(null);

        const jobTprNames = jobs.map((job) => job.tpr_name);
        setTprFiles(jobTprNames);
    };

    const cancelJob = async (tprName: string) => {
        setSelectedTpr(null);
        setTprFiles((prev) => prev.filter((tpr) => tpr !== tprName));
    };

    const stopJob = async (tprName: string) => {
        const { error } = await stop_tuner(experiment.id, tprName);
        if (error) showError(error);
        fetchTunerJobs();
    };

    const deleteJob = async (tprName: string) => {
        const { error } = await delete_tuner(experiment.id, tprName);
        if (error) showError(error);
        setSelectedTpr(null);
        fetchTunerJobs();
    };

    useEffect(() => {
        fetchTunerJobs();

        return () => {
            setTprFiles([]);
            setSelectedTpr(null);
        };
    }, [experiment.id]);

    return (
        <>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Stack direction="row" spacing={2} alignItems="center">
                    {tprFiles.length > 0 && (
                        <Tabs
                            value={selectedTpr || false}
                            onChange={handleChange}
                            variant="scrollable"
                            scrollButtons="auto"
                        >
                            {tprFiles.map((tprFile) => (
                                <Tab key={tprFile} value={tprFile} label={tprFile} />
                            ))}
                        </Tabs>
                    )}

                    <FileSelector
                        experimentId={experiment.id}
                        ext="tpr"
                        title="Select TPR file"
                        onFileSelected={newTpr}
                        width={300}
                    />
                </Stack>

                {tprFiles.length === 0 && experiment.step < 2 && (
                    <Button variant="contained" color="error" onClick={() => setConfirmSkipTuningDialog(true)}>
                        Skip tuning
                    </Button>
                )}
            </Stack>

            {selectedTpr && (
                <Box sx={{ mt: 2 }}>
                    <TunerView
                        tprName={selectedTpr}
                        cancelJob={cancelJob}
                        stopJob={stopJob}
                        deleteJob={deleteJob}
                        {...props}
                    />
                </Box>
            )}

            <ConfirmDialog
                open={confirmSkipTuningDialog}
                setOpen={setConfirmSkipTuningDialog}
                onConfirm={() => {
                    if (experiment.step < 2) nextStep();
                    else changeStep(2);
                }}
                message="Are you sure you want to skip the tuning step? You can always come back to it later."
            />
        </>
    );
};

export default TuneStep;

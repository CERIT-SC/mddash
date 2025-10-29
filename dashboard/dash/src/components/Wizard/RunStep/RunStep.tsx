import { useState, useEffect } from "react";

import { Box, Stack, Tabs, Tab } from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import FileSelector from "@/components/FileSelector";
import { delete_gmx, gmx_statuses } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";
import RunView from "./RunView";

const RunStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();
    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);

    const handleChange = (_: React.SyntheticEvent, newValue: string) => {
        setSelectedTpr(newValue);
    };

    const fetchGromacsJobs = async () => {
        const { data, error } = await gmx_statuses(experiment.id);
        if (error) showError(error);
        const jobs = data || [];

        const jobTprNames = jobs.map((job) => job.tpr_name);
        setTprFiles((prev) => [...new Set([...prev, ...jobTprNames])]);
    };

    const newTpr = (newSelectedTpr: string) => {
        if (!newSelectedTpr) return;

        const tprFile = newSelectedTpr.split("/").pop() || newSelectedTpr;
        setSelectedTpr(tprFile);

        if (!tprFiles.includes(tprFile)) {
            setTprFiles((prev) => [...prev, tprFile]);
        }
    };

    const deleteJob = async (tprName: string) => {
        const { error } = await delete_gmx(experiment.id, tprName);
        if (error) showError(error);
        setSelectedTpr(null);
        fetchGromacsJobs();
    };

    useEffect(() => {
        fetchGromacsJobs();

        return () => {
            setTprFiles([]);
            setSelectedTpr(null);
        };
    }, [experiment.id]);

    return (
        <>
            <Stack direction="row" spacing={2} alignItems="center">
                <Tabs value={selectedTpr || false} onChange={handleChange} variant="scrollable" scrollButtons="auto">
                    {tprFiles.map((tprFile) => (
                        <Tab key={tprFile} value={tprFile} label={tprFile} />
                    ))}
                </Tabs>

                <FileSelector
                    experimentId={experiment.id}
                    ext="tpr"
                    title="Select TPR file"
                    onFileSelected={newTpr}
                    width={300}
                />
            </Stack>

            {selectedTpr && (
                <Box sx={{ mt: 2 }}>
                    <RunView tprName={selectedTpr} deleteJob={deleteJob} {...props} />
                </Box>
            )}
        </>
    );
};

export default RunStep;

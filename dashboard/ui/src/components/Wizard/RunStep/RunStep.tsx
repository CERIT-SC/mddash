import { useState } from "react";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { useGromacsStatuses, useDeleteGmx } from "@/hooks/use-gromacs";
import ConfirmDialog from "@/components/ConfirmDialog";
import RunView from "./RunView";
import TprSelector from "../TprSelector";

const RunStep = (props: WizardStepProps) => {
    const { experiment } = props;

    const { data: gromacsJobs = [], refetch: refetchJobs } = useGromacsStatuses(experiment.id);
    const deleteGmx = useDeleteGmx(experiment.id);

    const existingJobs = gromacsJobs.map((job) => job.tpr_name);

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [localTprFiles, setLocalTprFiles] = useState<string[]>([]);
    const [deleteTpr, setDeleteTpr] = useState<string | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const allTprFiles = Array.from(new Set([...existingJobs, ...localTprFiles]));

    const handleAddTpr = (tpr: string) => {
        setLocalTprFiles((prev) => (prev.includes(tpr) ? prev : [...prev, tpr]));
        setSelectedTpr(tpr);
    };

    const handleDeleteTpr = (tpr: string) => {
        if (existingJobs.includes(tpr)) {
            setDeleteTpr(tpr);
            setConfirmDeleteDialog(true);
        } else {
            setSelectedTpr(null);
            setLocalTprFiles((prev) => prev.filter((t) => t !== tpr));
        }
    };

    const handleConfirmDelete = async () => {
        if (!deleteTpr) return;
        await deleteGmx.mutateAsync(deleteTpr);
        setSelectedTpr(null);
        setLocalTprFiles((prev) => prev.filter((t) => t !== deleteTpr));
        refetchJobs();
    };

    return (
        <div className="flex flex-col items-center gap-4 w-full">
            <div className="flex flex-row gap-4 w-[90%]">
                <TprSelector
                    experimentId={experiment.id}
                    title="Gromacs Jobs"
                    addTitle="Add Gromacs Job"
                    tprFiles={allTprFiles}
                    selectedTpr={selectedTpr}
                    onAddTpr={handleAddTpr}
                    onDeleteTpr={handleDeleteTpr}
                    onSelectTpr={setSelectedTpr}
                />

                {selectedTpr && (
                    <div className="flex-1">
                        <RunView tprName={selectedTpr} onStartJob={refetchJobs} {...props} />
                    </div>
                )}
            </div>

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={handleConfirmDelete}
                message="Are you sure you want to delete this GROMACS job? The data will be lost."
            />
        </div>
    );
};

export default RunStep;

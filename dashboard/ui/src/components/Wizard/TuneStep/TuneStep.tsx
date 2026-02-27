import { useState } from "react";

import { SkipForward } from "lucide-react";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { useTunerStatuses, useStopTuner, useDeleteTuner } from "@/hooks/use-tuner";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import TunerView from "./TunerView";
import TprSelector from "@/components/Wizard/TprSelector";

const TuneStep = (props: WizardStepProps) => {
    const { experiment } = props;

    const { data: tunerJobs = [], refetch: refetchJobs } = useTunerStatuses(experiment.id);
    const stopTuner = useStopTuner(experiment.id);
    const deleteTuner = useDeleteTuner(experiment.id);

    const tprFiles = tunerJobs.map((job) => job.tpr_name);
    const existingJobs = tprFiles;

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [localTprFiles, setLocalTprFiles] = useState<string[]>([]);
    const [deleteTpr, setDeleteTpr] = useState<string | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);
    const [skipDialog, setSkipDialog] = useState(false);

    // Merge server jobs into local list
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
        await deleteTuner.mutateAsync(deleteTpr);
        setSelectedTpr(null);
        setLocalTprFiles((prev) => prev.filter((t) => t !== deleteTpr));
        refetchJobs();
    };

    const handleStop = async (tprName: string) => {
        await stopTuner.mutateAsync(tprName);
        refetchJobs();
    };

    return (
        <div className="flex flex-col items-center gap-4 w-full">
            <div className="flex flex-row gap-4 w-[90%]">
                <TprSelector
                    experimentId={experiment.id}
                    title="Tuner Jobs"
                    addTitle="Add Tuner Job"
                    tprFiles={allTprFiles}
                    selectedTpr={selectedTpr}
                    onAddTpr={handleAddTpr}
                    onDeleteTpr={handleDeleteTpr}
                    onSelectTpr={setSelectedTpr}
                />

                {selectedTpr ? (
                    <div className="flex-1">
                        <TunerView tprName={selectedTpr} stopJob={handleStop} onStartTuner={refetchJobs} {...props} />
                    </div>
                ) : (
                    <div className="flex-1 flex justify-end items-start">
                        <Button
                            variant="outline"
                            className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
                            onClick={() => setSkipDialog(true)}
                        >
                            <SkipForward className="h-4 w-4 mr-1" />
                            Skip Tuning
                        </Button>
                    </div>
                )}
            </div>

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
                onConfirm={handleConfirmDelete}
                message="Are you sure you want to delete this tuning job? The data will be lost."
            />
        </div>
    );
};

export default TuneStep;

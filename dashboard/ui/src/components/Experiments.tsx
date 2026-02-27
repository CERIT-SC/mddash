import { useState } from "react";

import { Link } from "@tanstack/react-router";
import { Wand2, Trash2, PlusCircle, Loader2 } from "lucide-react";

import { Experiment, getPodStatusVariant, statusBadgeClass } from "@/util/types";
import { useExperiments, useDeleteExperiment } from "@/hooks/use-experiments";
import ConfirmDialog from "./ConfirmDialog";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const Experiments = () => {
    const { data: experiments = [], isLoading } = useExperiments();
    const deleteExperiment = useDeleteExperiment();

    const [experimentToDelete, setExperimentToDelete] = useState<Experiment | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const handleDeleteClick = (experiment: Experiment) => {
        setExperimentToDelete(experiment);
        setConfirmDeleteDialog(true);
    };

    const handleConfirmDelete = () => {
        if (experimentToDelete) {
            deleteExperiment.mutate(experimentToDelete.id);
            setExperimentToDelete(null);
        }
    };

    if (isLoading) {
        return (
            <div className="flex justify-center items-center min-h-48">
                <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="px-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {experiments.map((experiment) => {
                    const notebookStatus = experiment.notebook?.status || "UNKNOWN";
                    const podVariant = getPodStatusVariant(notebookStatus);
                    return (
                        <Card key={experiment.id} className="flex flex-col justify-between">
                            <CardContent className="pt-4 flex flex-col gap-1">
                                <h3 className="font-semibold text-base">{experiment.name}</h3>
                                <div className="flex items-center gap-1 text-sm">
                                    <span className="text-muted-foreground font-medium">Step:</span>
                                    <span>{experiment.step}</span>
                                </div>
                                <div className="flex items-center gap-1 text-sm">
                                    <span className="text-muted-foreground font-medium">Status:</span>
                                    <span>{experiment.status}</span>
                                </div>
                                <div className="flex items-center gap-1 text-sm">
                                    <span className="text-muted-foreground font-medium">Notebook:</span>
                                    <Badge variant="outline" className={cn("text-xs", statusBadgeClass(podVariant))}>
                                        {notebookStatus}
                                    </Badge>
                                </div>
                                <div className="flex items-center gap-1 text-sm">
                                    <span className="text-muted-foreground font-medium">Tuner jobs:</span>
                                    <span>{experiment.tuner_jobs.length}</span>
                                </div>
                                <div className="flex items-center gap-1 text-sm">
                                    <span className="text-muted-foreground font-medium">Gromacs jobs:</span>
                                    <span>{experiment.gromacs_jobs.length}</span>
                                </div>
                            </CardContent>
                            <CardFooter className="flex justify-center gap-2 pt-0">
                                <Button size="sm" asChild>
                                    <Link to="/$id/wizard" params={{ id: experiment.id }}>
                                        <Wand2 className="h-4 w-4 mr-1" />
                                        Wizard
                                    </Link>
                                </Button>
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
                                    onClick={() => handleDeleteClick(experiment)}
                                >
                                    <Trash2 className="h-4 w-4 mr-1" />
                                    Delete
                                </Button>
                            </CardFooter>
                        </Card>
                    );
                })}

                {/* New experiment card */}
                <Link to="/new" className="no-underline">
                    <Card className="flex flex-col items-center justify-center min-h-40 border-2 border-dashed text-muted-foreground cursor-pointer hover:border-primary hover:text-primary transition-colors h-full">
                        <CardContent className="flex flex-col items-center gap-2 py-6">
                            <PlusCircle className="h-16 w-16" />
                            <span className="text-lg font-medium">New</span>
                        </CardContent>
                    </Card>
                </Link>
            </div>

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={handleConfirmDelete}
                message="Are you sure you want to delete this experiment? All data will be lost."
            />
        </div>
    );
};

export default Experiments;

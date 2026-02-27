import React, { useState } from "react";

import { useParams } from "@tanstack/react-router";
import { Pencil, Check, X, Loader2 } from "lucide-react";

import WizardStepper from "@/components/Wizard/Stepper";
import { useExperiment, useEditExperiment } from "@/hooks/use-experiment";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const Wizard = () => {
    const { id } = useParams({ from: "/$id/wizard" });
    const { data: experiment, isLoading } = useExperiment(id);
    const editExperiment = useEditExperiment();

    const [editingName, setEditingName] = useState(false);
    const [nameInput, setNameInput] = useState("");

    const handleEditClick = () => {
        if (experiment) {
            setNameInput(experiment.name);
            setEditingName(true);
        }
    };

    const handleNameSave = async () => {
        if (experiment && nameInput.trim() && nameInput !== experiment.name) {
            editExperiment.mutate({ id: experiment.id, data: { name: nameInput.trim() } });
        }
        setEditingName(false);
    };

    const handleNameCancel = () => {
        setEditingName(false);
        setNameInput("");
    };

    const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") handleNameSave();
        else if (e.key === "Escape") handleNameCancel();
    };

    return (
        <div className="flex flex-col gap-4">
            <h1 className="text-3xl font-bold">Wizard</h1>

            <div className="flex items-center justify-center" style={{ minHeight: 56 }}>
                {isLoading ? (
                    <p className="text-muted-foreground">Loading...</p>
                ) : experiment ? (
                    <Card className="flex items-center px-4 py-2">
                        {editingName ? (
                            <div className="flex items-center gap-1">
                                <Input
                                    value={nameInput}
                                    onChange={(e) => setNameInput(e.target.value)}
                                    onBlur={handleNameSave}
                                    onKeyDown={handleNameKeyDown}
                                    autoFocus
                                    className="min-w-64 max-w-xl"
                                />
                                <Button variant="ghost" size="icon" aria-label="Save" onClick={handleNameSave}>
                                    <Check className="h-4 w-4" />
                                </Button>
                                <Button variant="ghost" size="icon" aria-label="Cancel" onClick={handleNameCancel}>
                                    <X className="h-4 w-4" />
                                </Button>
                            </div>
                        ) : (
                            <div className="flex items-center gap-1">
                                <span className="text-lg font-semibold mr-1">{experiment.name}</span>
                                <Button variant="ghost" size="icon" aria-label="Edit name" onClick={handleEditClick}>
                                    <Pencil className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                    </Card>
                ) : null}
            </div>

            {isLoading ? (
                <div className="flex justify-center mt-6">
                    <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
                </div>
            ) : experiment ? (
                <Card className="p-6 mt-2">
                    <WizardStepper experiment={experiment} />
                </Card>
            ) : null}
        </div>
    );
};

export default Wizard;

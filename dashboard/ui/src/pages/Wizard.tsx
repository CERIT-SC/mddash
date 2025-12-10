import { useParams } from "react-router-dom";
import { Paper, Typography, CircularProgress, TextField, IconButton } from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import { useEffect, useState, useCallback } from "react";

import WizardStepper from "@/components/Wizard/Stepper";
import { Experiment } from "@/util/types";
import { get_experiment, edit_experiment } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";

const Wizard = () => {
    const { id } = useParams<{ id: string }>();
    const { showError } = useNotification();

    const [experiment, setExperiment] = useState<Experiment | null>(null);
    const [editingName, setEditingName] = useState(false);
    const [nameInput, setNameInput] = useState("");

    const getExperiment = useCallback(async () => {
        if (!id) return;

        const { data, error } = await get_experiment(id);
        if (error) showError(error);
        setExperiment(data || null);
    }, [id, showError]);

    useEffect(() => {
        getExperiment();
    }, [getExperiment]);

    const editExperimentName = async (newName: string) => {
        if (!experiment || newName === experiment.name) return;
        const { data, error } = await edit_experiment(experiment.id, { name: newName });
        if (error) {
            showError(error);
        } else if (data) {
            setExperiment(data);
        }
    };

    const handleEditClick = () => {
        if (experiment) {
            setNameInput(experiment.name);
            setEditingName(true);
        }
    };

    const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setNameInput(e.target.value);
    };

    const handleNameSave = async () => {
        if (experiment && nameInput.trim() && nameInput !== experiment.name) {
            await editExperimentName(nameInput.trim());
        }
        setEditingName(false);
    };

    const handleNameCancel = () => {
        setEditingName(false);
        setNameInput("");
    };

    const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
            handleNameSave();
        } else if (e.key === "Escape") {
            handleNameCancel();
        }
    };

    return (
        <>
            <Typography variant="h1">Wizard</Typography>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 56 }}>
                {experiment ? (
                    <Paper elevation={2} sx={{ display: "flex", alignItems: "center", px: 2, py: 1 }}>
                        {editingName ? (
                            <>
                                <TextField
                                    value={nameInput}
                                    onChange={handleNameChange}
                                    onBlur={handleNameSave}
                                    onKeyDown={handleNameKeyDown}
                                    size="small"
                                    autoFocus
                                    variant="outlined"
                                    sx={{ minWidth: "40vw", maxWidth: "80vw" }}
                                />
                                <IconButton aria-label="Save" onClick={handleNameSave} size="small">
                                    <CheckIcon fontSize="small" />
                                </IconButton>
                                <IconButton aria-label="Cancel" onClick={handleNameCancel} size="small">
                                    <CloseIcon fontSize="small" />
                                </IconButton>
                            </>
                        ) : (
                            <>
                                <Typography variant="h4" sx={{ textAlign: "center", mr: 1 }}>
                                    {experiment.name}
                                </Typography>
                                <IconButton aria-label="Edit name" onClick={handleEditClick} size="small">
                                    <EditIcon fontSize="small" />
                                </IconButton>
                            </>
                        )}
                    </Paper>
                ) : (
                    <Typography variant="h4" sx={{ textAlign: "center" }}>
                        Loading...
                    </Typography>
                )}
            </div>

            {(experiment && (
                <Paper elevation={2} sx={{ p: 4, mt: 2 }}>
                    <WizardStepper experiment={experiment} setExperiment={setExperiment} />
                </Paper>
            )) || (
                <div style={{ display: "flex", justifyContent: "center", marginTop: "20px" }}>
                    <CircularProgress />
                </div>
            )}
        </>
    );
};

export default Wizard;

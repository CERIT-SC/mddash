import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    Stack,
    Paper,
    Button,
    TextField,
    Typography,
    FormControl,
    FormLabel,
    Tabs,
    Tab,
    FormHelperText,
} from "@mui/material";

import Dropzone from "@/components/Dropzone";
import { create_experiment } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";

const tabStyles = {
    textTransform: "none",
    borderRadius: 1,
    border: 1,
    color: "text.secondary",
    bgcolor: "background.paper",
    borderColor: "divider",
    "&.Mui-selected": {
        color: "primary.contrastText",
        bgcolor: "primary.main",
        borderColor: "text.primary",
    },
    "&:not(.Mui-selected):hover": {
        bgcolor: "action.hover",
        color: "text.primary",
    },
} as const;

const New = () => {
    const navigate = useNavigate();
    const { showError, showSuccess } = useNotification();

    const [name, setName] = useState("");
    const [type, setType] = useState("");
    const [pdbId, setPdbId] = useState("");
    const [repoUrl, setRepoUrl] = useState("");
    const [files, setFiles] = useState<File[]>([]);

    const [nameError, setNameError] = useState(false);
    const [typeError, setTypeError] = useState(false);
    const [typeAuxError, setTypeAuxError] = useState(false);

    const validateForm = () => {
        let typeAuxError = false;

        if ((type === "pdb" && !pdbId) || (type === "repo" && !repoUrl) || (type === "file" && files.length === 0))
            typeAuxError = true;

        setNameError(!name);
        setTypeError(!type);
        setTypeAuxError(typeAuxError);

        if (name && type && !typeAuxError) return true;

        showError("Please fill in all required fields");
        return false;
    };

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();

        if (!validateForm()) return;

        const formData = new FormData();
        formData.append("experiment-name", name);
        formData.append("type", type);
        if (type === "pdb") formData.append("pdb-id", pdbId);
        if (type === "repo") formData.append("repo-url", repoUrl);
        if (type === "file" && files.length > 0) {
            files.forEach((file) => formData.append("simulation-files", file));
        }

        const { data, error } = await create_experiment(formData);

        if (error) {
            showError(error);
            return;
        }

        console.log("Experiment created:", data);
        showSuccess("Experiment created successfully!");
        navigate(`/${data!.id}/wizard`);
    };

    const handleTypeChange = (_: React.SyntheticEvent, newType: string | false) => {
        if (typeof newType !== "string") return;
        setType(newType);
        setPdbId("");
        setRepoUrl("");
        setFiles([]);
    };

    return (
        <>
            <Typography variant="h1" gutterBottom align="center">
                New Experiment
            </Typography>

            <Paper elevation={2} sx={{ maxWidth: 640, mx: "auto" }}>
                <Stack component="form" autoComplete="off" onSubmit={handleSubmit} spacing={4} p={4} sx={{ width: 1 }}>
                    <TextField
                        name="experiment-name"
                        label="Name"
                        variant="outlined"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        error={nameError}
                    />

                    <FormControl error={typeError || typeAuxError}>
                        <FormLabel>Initial Data</FormLabel>
                        <Tabs
                            value={type || false}
                            onChange={handleTypeChange}
                            aria-label="Initial data source"
                            variant="fullWidth"
                            TabIndicatorProps={{ style: { display: "none" } }}
                            sx={{ mt: 1 }}
                        >
                            <Tab value="file" label="Upload Files" disableRipple sx={tabStyles} />
                            <Tab value="pdb" label="PDB ID" disableRipple sx={tabStyles} />
                            <Tab value="repo" label="Repository URL" disableRipple sx={tabStyles} />
                        </Tabs>
                        {(typeError || typeAuxError) && (
                            <FormHelperText>Select a source and fill its required details.</FormHelperText>
                        )}
                    </FormControl>

                    {type === "pdb" && (
                        <TextField
                            id="pdb-id"
                            label="PDB ID"
                            variant="outlined"
                            value={pdbId}
                            onChange={(e) => setPdbId(e.target.value)}
                            error={typeAuxError}
                        />
                    )}
                    {type === "repo" && (
                        <TextField
                            id="repo-url"
                            label="Repository URL"
                            variant="outlined"
                            value={repoUrl}
                            onChange={(e) => setRepoUrl(e.target.value)}
                            error={typeAuxError}
                        />
                    )}
                    {type === "file" && (
                        <Dropzone inputName="simulation-files" onDrop={(acceptedFiles) => setFiles(acceptedFiles)} />
                    )}

                    <Button variant="contained" type="submit" sx={{ alignSelf: "flex-start" }}>
                        Create Experiment
                    </Button>
                </Stack>
            </Paper>
        </>
    );
};

export default New;

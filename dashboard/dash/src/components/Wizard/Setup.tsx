import { useEffect, useState } from "react";
import { Box, Stack, Button, Typography, CircularProgress } from "@mui/material";

import { WizardStepperProps } from "./Stepper";
import { get_notebook, spawn_notebook, delete_notebook } from "../../util/api";

const WizardSetup = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;
    const [loading, setLoading] = useState(false);
    const [notebookUp, setNotebookUp] = useState(false);
    const [notebookPath, setNotebookPath] = useState("");

    const getNotebook = async () => {
        setLoading(true);
        const { data, error } = await get_notebook(experiment.id);
        setErrorMessage(error || "");
        setNotebookUp(data?.message === "up");
        setNotebookPath(data?.path || "");
        setLoading(false);
    };

    const spawnNotebook = async () => {
        const { error } = await spawn_notebook(experiment.id);
        setErrorMessage(error || "");
        getNotebook();
    };

    const deleteNotebook = async () => {
        const { error } = await delete_notebook(experiment.id);
        setErrorMessage(error || "");
        getNotebook();
    };

    useEffect(() => {
        getNotebook();
    }, []);

    return (
        <Box sx={{ p: 4, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <Typography variant="h4" gutterBottom>
                {experiment.source_message}
            </Typography>
            {(loading && <CircularProgress />) || (
                <Stack spacing={2} direction="column">
                    {(notebookUp && (
                        <>
                            <Typography variant="h5">Notebook running 🚀</Typography>
                            <Button variant="contained" color="success" href={notebookPath} target="_blank">
                                Open Jupyter Notebook
                            </Button>
                            <Button variant="contained" color="error" onClick={deleteNotebook}>
                                Delete Jupyter Notebook
                            </Button>
                        </>
                    )) || (
                        <>
                            <Typography variant="h5">Notebook down 💔</Typography>
                            <Button variant="contained" color="primary" onClick={spawnNotebook}>
                                Spawn Jupyter Notebook
                            </Button>
                        </>
                    )}
                </Stack>
            )}
        </Box>
    );
};

export default WizardSetup;

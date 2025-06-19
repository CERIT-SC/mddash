import { useEffect, useState } from "react";
import { Stack, Button, Typography, CircularProgress } from "@mui/material";

import { WizardStepProps } from "./Stepper";
import { get_notebook, spawn_notebook, delete_notebook } from "../../util/api";
import ConfirmDialog from "../ConfirmDialog";

const WizardSetup = (props: WizardStepProps) => {
    const { experiment, setErrorMessage, nextStep } = props;
    const [loading, setLoading] = useState(false);
    const [notebookUp, setNotebookUp] = useState(false);
    const [notebookPath, setNotebookPath] = useState("");
    const [nextStepDialog, setNextStepDialog] = useState(false);

    const getNotebook = async () => {
        setLoading(true);
        const { data, error } = await get_notebook(experiment.id);
        setErrorMessage(error || "");
        setNotebookUp(data?.up || false);
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
        <Stack direction="column" alignItems="center" spacing={5}>
            <Stack direction="row" justifyContent="space-between" width="100%">
                <Typography variant="h6">
                    {experiment.source_message}
                </Typography>
                {experiment.step === 0 && (
                    <Button variant="contained" color="error" onClick={() => setNextStepDialog(true)}>
                        Complete Setup
                    </Button>
                )}
            </Stack>
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

            <ConfirmDialog
                open={nextStepDialog}
                setOpen={setNextStepDialog}
                title="Complete Setup?"
                message="Are you sure you want to proceed to the next step? Setup doesn't appear to be complete in the notebook. Stuff may break later."
                onConfirm={nextStep}
            />
        </Stack>
    );
};

export default WizardSetup;

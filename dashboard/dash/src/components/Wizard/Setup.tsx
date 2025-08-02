import { useEffect, useState } from "react";
import { Stack, Button, Typography, CircularProgress } from "@mui/material";

import { WizardStepProps } from "./Stepper";
import { get_notebook, spawn_notebook, delete_notebook } from "../../util/api";
import ConfirmDialog from "../ConfirmDialog";
import { NotebookStatus, PodStatus } from "../../util/types";

const WizardSetup = (props: WizardStepProps) => {
    const { experiment, setErrorMessage, nextStep } = props;
    const [loading, setLoading] = useState(false);
    const [notebookStatus, setNotebookStatus] = useState<NotebookStatus>({ status: "UNKNOWN", path: "" });
    const [nextStepDialog, setNextStepDialog] = useState(false);

    const fetchStatus = async () => {
        const { data, error } = await get_notebook(experiment.id);
        if (error) setErrorMessage(error);
        setNotebookStatus(data || { status: "UNKNOWN", path: "" });
    };

    const spawnNotebook = async () => {
        const { error, data } = await spawn_notebook(experiment.id);
        setErrorMessage(error || "");
        setNotebookStatus(data || { status: "UNKNOWN", path: "" });
    };

    const deleteNotebook = async () => {
        const { error } = await delete_notebook(experiment.id);
        setErrorMessage(error || "");
        fetchStatus();
    };

    const respawnNotebook = async () => {
        await deleteNotebook();
        await spawnNotebook();
    };

    useEffect(() => {
        setLoading(true);
        fetchStatus().finally(() => setLoading(false));

        let intervalId: number | null = null;

        // actively poll the notebook status if it's pending or terminating
        if (notebookStatus.status === "PENDING" || notebookStatus.status === "TERMINATING") {
            intervalId = window.setInterval(fetchStatus, 1000);
        } else if (intervalId !== null) {
            console.log("Clearing tuner status interval as notebook is not pending.");
            window.clearInterval(intervalId);
        }

        return () => {
            if (intervalId !== null) {
                console.log("Clearing tuner status interval.");
                window.clearInterval(intervalId);
            }
        };
    }, [notebookStatus.status]);

    return (
        <Stack direction="column" alignItems="center" spacing={5}>
            <Stack direction="row" justifyContent="space-between" width="100%">
                <Typography variant="h4">{experiment.source_message}</Typography>
                {experiment.step === 0 && (
                    <Button variant="contained" color="error" onClick={() => setNextStepDialog(true)}>
                        Complete Setup
                    </Button>
                )}
            </Stack>
            {(loading && <CircularProgress />) || (
                <Stack spacing={2} direction="column">
                    {notebookStatus.status === "RUNNING" && (
                        <>
                            <Typography variant="h4" color={PodStatus.getColor(notebookStatus.status)}>
                                Notebook running 🚀
                            </Typography>
                            <Button variant="contained" color="success" href={notebookStatus.path} target="_blank">
                                Open Jupyter Notebook
                            </Button>
                            <Button variant="contained" color="error" onClick={deleteNotebook}>
                                Delete Jupyter Notebook
                            </Button>
                        </>
                    )}

                    {(notebookStatus.status === "PENDING" || notebookStatus.status === "TERMINATING") && (
                        <>
                            <Typography variant="h4" color={PodStatus.getColor(notebookStatus.status)}>
                                {notebookStatus.status === "PENDING"
                                    ? "Notebook starting ⏳"
                                    : "Notebook terminating ⏳"}
                            </Typography>
                            <CircularProgress size={40} />
                            <Typography variant="body1" color={PodStatus.getColor(notebookStatus.status)}>
                                {notebookStatus.status === "PENDING"
                                    ? "Please wait while the notebook is being prepared..."
                                    : "Please wait while the notebook is being terminated..."}
                            </Typography>
                            {notebookStatus.status === "PENDING" && (
                                <Button variant="contained" color="error" onClick={deleteNotebook}>
                                    Delete Jupyter Notebook
                                </Button>
                            )}
                        </>
                    )}

                    {(notebookStatus.status === "TERMINATED" || notebookStatus.status === "ERROR") && (
                        <>
                            <Typography variant="h4" color={PodStatus.getColor(notebookStatus.status)}>
                                {notebookStatus.status === "TERMINATED"
                                    ? "Notebook terminated 🛑"
                                    : "Notebook error ❌"}
                            </Typography>
                            <Button variant="contained" color="primary" onClick={respawnNotebook}>
                                Restart Jupyter Notebook
                            </Button>
                        </>
                    )}

                    {(notebookStatus.status === "DOWN" || notebookStatus.status === "UNKNOWN") && (
                        <>
                            <Typography variant="h4" color={PodStatus.getColor(notebookStatus.status)}>
                                {notebookStatus.status === "DOWN" ? "Notebook down 💔" : "Notebook status unknown ❓"}
                            </Typography>
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

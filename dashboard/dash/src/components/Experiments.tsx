import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
    Typography,
    Card,
    CardActionArea,
    CardActions,
    Grid2 as Grid,
    Stack,
    CardContent,
    Button,
} from "@mui/material";
import { AddCircleOutline } from "@mui/icons-material";
import { BASE_PATH } from "../util/const";

import { Experiment, PodStatus } from "../util/types";
import { delete_experiment, get_experiments } from "../util/api";
import ErrorMessage from "./ErrorMessage";
import ConfirmDialog from "./ConfirmDialog";

const Experiments = () => {
    const [experiments, setExperiments] = useState<Experiment[]>([]);
    const [errorMessage, setErrorMessage] = useState<string>("");
    const [experimentToDelete, setExperimentToDelete] = useState<Experiment | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState<boolean>(false);

    const getExperiments = async () => {
        const { data, error } = await get_experiments();
        setErrorMessage(error || "");
        setExperiments(data || []);
    };

    const deleteExperiment = async (id: string) => {
        const { error } = await delete_experiment(id);
        setErrorMessage(error || "");

        if (!error) getExperiments();
    };

    useEffect(() => {
        getExperiments();
    }, []);

    return (
        <Stack spacing={2} p={4}>
            <Grid container spacing={2}>
                {experiments.map((experiment) => (
                    <Grid size={3} key={experiment.id} sx={{ display: "flex" }}>
                        <Card
                            sx={{
                                padding: 2,
                                flexGrow: 1,
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                            }}
                        >
                            <CardContent>
                                <Typography variant="h3">{experiment.name}</Typography>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Step:</Typography>
                                    <Typography variant="body2">{experiment.step}</Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Status:</Typography>
                                    <Typography variant="body2">{experiment.status}</Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Notebook:</Typography>
                                    <Typography variant="body2" color={PodStatus.getColor(experiment.notebook_status)}>
                                        {experiment.notebook_status}
                                    </Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Tuner jobs:</Typography>
                                    <Typography variant="body2">
                                        {
                                            Object.values(experiment.tuner_jobs).filter(
                                                (j) => j.summary && j.summary.RUNNING > 0
                                            ).length
                                        }
                                    </Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Gromacs jobs:</Typography>
                                    <Typography variant="body2">
                                        {
                                            Object.values(experiment.gromacs_jobs).filter((j) => j.status === "RUNNING")
                                                .length
                                        }
                                    </Typography>
                                </Stack>
                            </CardContent>
                            <CardActions sx={{ alignSelf: "flex-end", width: "100%", justifyContent: "center" }}>
                                <Button
                                    size="small"
                                    variant="contained"
                                    component={Link}
                                    to={`${BASE_PATH}/${experiment.id}/wizard`}
                                >
                                    Wizard
                                </Button>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    color="error"
                                    onClick={() => {
                                        setExperimentToDelete(experiment);
                                        setConfirmDeleteDialog(true);
                                    }}
                                >
                                    Delete
                                </Button>
                            </CardActions>
                        </Card>
                    </Grid>
                ))}

                <Grid size={3} sx={{ display: "flex" }}>
                    <Card
                        sx={{
                            flexGrow: 1,
                            height: "100%",
                            display: "flex",
                            color: "text.secondary",
                            border: "4px dashed",
                        }}
                    >
                        <CardActionArea
                            component={Link}
                            to={`${BASE_PATH}/new`}
                            sx={{ height: "100%", display: "flex", flexDirection: "column" }}
                        >
                            <Stack alignItems="center" justifyContent="center" spacing={2} p={4} sx={{ flexGrow: 1 }}>
                                <AddCircleOutline sx={{ width: 75, height: 75 }} />
                                <Typography variant="h3" textAlign="center">
                                    New
                                </Typography>
                            </Stack>
                        </CardActionArea>
                    </Card>
                </Grid>
            </Grid>

            {errorMessage && <ErrorMessage message={errorMessage} />}

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => {
                    deleteExperiment(experimentToDelete!.id);
                    setExperimentToDelete(null);
                }}
                message="Are you sure you want to delete this experiment? All data will be lost."
            />
        </Stack>
    );
};

export default Experiments;

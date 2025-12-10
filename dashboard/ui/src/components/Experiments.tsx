import { useState, useEffect, useCallback } from "react";

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
    CircularProgress,
    Box,
} from "@mui/material";
import { AddCircleOutline, AutoFixHigh, Delete } from "@mui/icons-material";

import { Experiment, getPodStatusColor } from "@/util/types";
import { delete_experiment, get_experiments } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import ConfirmDialog from "./ConfirmDialog";

const Experiments = () => {
    const [experiments, setExperiments] = useState<Experiment[]>([]);
    const [loading, setLoading] = useState(true);
    const { showError } = useNotification();
    const [experimentToDelete, setExperimentToDelete] = useState<Experiment | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchExperiments = useCallback(async () => {
        setLoading(true);
        const { data, error } = await get_experiments();
        if (error) {
            showError(error);
        } else {
            setExperiments(data || []);
        }
        setLoading(false);
    }, [showError]);

    const handleDeleteExperiment = useCallback(
        async (id: string) => {
            const { error } = await delete_experiment(id);
            if (error) {
                showError(error);
            } else {
                fetchExperiments();
            }
        },
        [showError, fetchExperiments],
    );

    const handleDeleteClick = useCallback((experiment: Experiment) => {
        setExperimentToDelete(experiment);
        setConfirmDeleteDialog(true);
    }, []);

    const handleConfirmDelete = useCallback(() => {
        if (experimentToDelete) {
            handleDeleteExperiment(experimentToDelete.id);
            setExperimentToDelete(null);
        }
    }, [experimentToDelete, handleDeleteExperiment]);

    useEffect(() => {
        fetchExperiments();
    }, [fetchExperiments]);

    if (loading) {
        return (
            <Box display="flex" justifyContent="center" alignItems="center" minHeight="300px">
                <CircularProgress size={60} />
            </Box>
        );
    }

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
                                    <Typography
                                        variant="body2"
                                        color={getPodStatusColor(experiment.notebook?.status || "UNKNOWN")}
                                    >
                                        {experiment.notebook?.status || "UNKNOWN"}
                                    </Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Tuner jobs:</Typography>
                                    <Typography variant="body2">{experiment.tuner_jobs.length}</Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Typography variant="subtitle2">Gromacs jobs:</Typography>
                                    <Typography variant="body2">{experiment.gromacs_jobs.length}</Typography>
                                </Stack>
                            </CardContent>
                            <CardActions sx={{ alignSelf: "flex-end", width: "100%", justifyContent: "center" }}>
                                <Button
                                    size="small"
                                    variant="contained"
                                    component={Link}
                                    to={`/${experiment.id}/wizard`}
                                    startIcon={<AutoFixHigh />}
                                >
                                    Wizard
                                </Button>
                                <Button
                                    size="small"
                                    variant="outlined"
                                    color="error"
                                    onClick={() => handleDeleteClick(experiment)}
                                    startIcon={<Delete />}
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
                            border: "2px dashed",
                        }}
                    >
                        <CardActionArea
                            component={Link}
                            to="/new"
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

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={handleConfirmDelete}
                message="Are you sure you want to delete this experiment? All data will be lost."
            />
        </Stack>
    );
};

export default Experiments;

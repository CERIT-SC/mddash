import React, { useEffect, useState } from "react";
import {
    Box,
    Stack,
    Button,
    Typography,
    CircularProgress,
    TableContainer,
    Table,
    TableHead,
    TableRow,
    TableCell,
    TableBody,
    Paper,
    Tooltip,
    Tabs,
    Tab,
} from "@mui/material";
import { tableCellClasses } from "@mui/material/TableCell";
import { styled } from "@mui/material/styles";

import { WizardStepperProps } from "./Stepper";
import { tuner_status, run_tuner, delete_tuner } from "../../util/api";
import { TunerStatus, TunerTrial } from "../../util/types";
import FileSelector from "../FileSelector";
import ConfirmDialog from "../ConfirmDialog";

const StyledTableCell = styled(TableCell)(({ theme }) => ({
    [`&.${tableCellClasses.head}`]: {
        backgroundColor: theme.palette.primary.main,
        color: theme.palette.common.white,
    },
    [`&.${tableCellClasses.body}`]: {
        fontSize: 14,
    },
}));

interface TunerTableProps {
    rows: TunerTrial[];
    selectedTrial: string | null;
    setSelectedTrial: (trialId: string | null) => void;
}

const TunerTable = (props: TunerTableProps) => {
    const { rows, selectedTrial, setSelectedTrial } = props;

    if (!rows || rows.length === 0) {
        return <Typography>No tuning trials available yet...</Typography>;
    }

    return (
        <TableContainer component={Paper}>
            <Table sx={{ minWidth: 650 }} aria-label="tuner trials table">
                <TableHead sx={{ backgroundColor: "primary.main" }}>
                    <TableRow>
                        <StyledTableCell>Select</StyledTableCell>
                        <StyledTableCell>Status</StyledTableCell>
                        <Tooltip title="Measured performance (ns/day)">
                            <StyledTableCell align="right">Performance</StyledTableCell>
                        </Tooltip>
                        <Tooltip title="Particle Mesh Ewald offload setting">
                            <StyledTableCell align="right">PME</StyledTableCell>
                        </Tooltip>
                        <Tooltip title="Non-bonded kernel type">
                            <StyledTableCell align="right">NB</StyledTableCell>
                        </Tooltip>
                        <Tooltip title="Number of MPI Processes">
                            <StyledTableCell align="right">NP</StyledTableCell>
                        </Tooltip>
                        <Tooltip title="Number of OpenMP Threads">
                            <StyledTableCell align="right">NTOMP</StyledTableCell>
                        </Tooltip>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {rows
                        .sort((a, b) => {
                            if (a.performance === null && b.performance === null) return 0;
                            if (a.performance === null) return 1;
                            if (b.performance === null) return -1;
                            return b.performance - a.performance;
                        })
                        .map((row) => (
                            <TableRow key={row.id} sx={{ "&:last-child td, &:last-child th": { border: 0 } }}>
                                <StyledTableCell>
                                    <input
                                        type="radio"
                                        name="selectedTrial"
                                        checked={selectedTrial === row.id}
                                        onClick={() => setSelectedTrial(selectedTrial === row.id ? null : row.id)}
                                    />
                                </StyledTableCell>
                                <StyledTableCell>{row.status}</StyledTableCell>
                                <StyledTableCell align="right">
                                    {row.performance !== null ? row.performance.toFixed(2) : "N/A"}
                                </StyledTableCell>
                                <StyledTableCell align="right">{row.pme}</StyledTableCell>
                                <StyledTableCell align="right">{row.nb}</StyledTableCell>
                                <StyledTableCell align="right">{row.np}</StyledTableCell>
                                <StyledTableCell align="right">{row.ntomp}</StyledTableCell>
                            </TableRow>
                        ))}
                </TableBody>
            </Table>
        </TableContainer>
    );
};

interface TunerViewProps extends WizardStepperProps {
    tprName: string;
    deleteJob: (tprName: string) => void;
}

const TunerView = (props: TunerViewProps) => {
    const { experiment, tprName, setErrorMessage, deleteJob } = props;

    const [loading, setLoading] = useState(false);
    const [tunerRunning, setTunerRunning] = useState(false);
    const [tunerStatus, setTunerStatus] = useState<TunerStatus | null>(null);
    const [selectedTrial, setSelectedTrial] = useState<string | null>(null);

    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);
    const [confirmRunDialog, setConfirmRunDialog] = useState(false);

    const fetchStatus = async (showError: boolean) => {
        const { data, error } = await tuner_status(experiment.id, tprName);
        if (showError && error) setErrorMessage(error);
        setTunerStatus(data?.data || null);
        setTunerRunning(!!data?.data);
    };

    const runTuner = async () => {
        const { error } = await run_tuner(experiment.id, tprName);
        setErrorMessage(error || "");
        fetchStatus(true);
    };

    const runSimulation = async () => {
        console.log(`Running trial ${selectedTrial}...`);
        // TODO: Run simulation
    };

    useEffect(() => {
        setLoading(true);
        fetchStatus(false).finally(() => setLoading(false));

        let intervalId: number | null = null;

        // refresh tuner status every 5 seconds if the tuner is up
        if (tunerRunning) {
            intervalId = window.setInterval(() => {
                fetchStatus(true);
            }, 5000);
        }

        return () => {
            if (intervalId !== null) {
                console.log("Clearing tuner status interval.");
                window.clearInterval(intervalId);
            }
        };
    }, [tprName, experiment.id, tunerRunning]);

    return (
        <>
            {(loading && (
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                    <CircularProgress />
                </Box>
            )) || (
                <Stack spacing={2} direction="column">
                    {(tunerRunning && (
                        <>
                            <TunerTable
                                rows={tunerStatus?.trials || []}
                                selectedTrial={selectedTrial}
                                setSelectedTrial={setSelectedTrial}
                            />

                            <Stack direction="row" spacing={2} justifyContent="space-between">
                                <Button variant="contained" color="error" onClick={() => setConfirmDeleteDialog(true)}>
                                    Delete tune job 🗑️
                                </Button>

                                {selectedTrial && (
                                    <Button variant="contained" onClick={() => setConfirmRunDialog(true)}>
                                        Run simulation with selected parameters ▶️
                                    </Button>
                                )}
                            </Stack>
                        </>
                    )) || (
                        <>
                            <Typography variant="h5">Tuner isn't running 💔</Typography>
                            <Button variant="contained" color="primary" onClick={runTuner}>
                                Start tune job 🏃
                            </Button>
                        </>
                    )}
                </Stack>
            )}

            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(tprName)}
                message="Are you sure you want to delete this tuning job? The data will be lost."
            />

            <ConfirmDialog
                open={confirmRunDialog}
                setOpen={setConfirmRunDialog}
                onConfirm={runSimulation}
                message="Are you sure you want to run simulation with these parameters?"
                confirmColor="primary"
            />
        </>
    );
};

const WizardTune = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tunerJobs, setTunerJobs] = useState<Record<string, any>>({});

    const handleChange = (_: React.SyntheticEvent, newValue: string) => {
        setSelectedTpr(newValue);
    };

    const newTpr = (newSelectedTpr: string) => {
        const tprFile = newSelectedTpr.split("/").pop() || newSelectedTpr;
        setSelectedTpr(tprFile);

        if (tunerJobs[tprFile]) return; // If the TPR file is already getting tuned, do nothing

        setTunerJobs((prev) => ({
            ...prev,
            [tprFile]: {
                tuner_run_id: `${experiment.id}-${tprFile}`,
                trials: [],
            },
        }));
    };

    const fetchTunerJobs = async () => {
        const { data, error } = await tuner_status(experiment.id);
        setErrorMessage(error || "");
        const jobs = data.data || {};

        console.log("Fetched tuner jobs:", jobs);

        if (Object.keys(jobs).length === 0) setSelectedTpr(null);
        setTunerJobs(jobs);
    };

    const deleteJob = async (tprName: string) => {
        const { error } = await delete_tuner(experiment.id, tprName);
        setErrorMessage(error || "");
        setSelectedTpr(null);
        fetchTunerJobs();
    };

    useEffect(() => {
        fetchTunerJobs();

        return () => {
            console.log("Cleaning up tuner jobs.");
            setTunerJobs({});
            setSelectedTpr(null);
        };
    }, [experiment.id, setErrorMessage]);

    return (
        <>
            <Tabs value={selectedTpr} onChange={handleChange} variant="scrollable" scrollButtons="auto">
                {Object.keys(tunerJobs).map((tprFile) => (
                    <Tab label={tprFile} value={tprFile} />
                ))}

                <FileSelector experimentId={experiment.id} extension="tpr" onFileSelected={newTpr} width={300} />
            </Tabs>

            {selectedTpr && (
                <Box sx={{ mt: 2 }}>
                    <TunerView
                        tprName={selectedTpr}
                        experiment={experiment}
                        setExperiment={props.setExperiment}
                        setErrorMessage={setErrorMessage}
                        deleteJob={deleteJob}
                    />
                </Box>
            )}
        </>
    );
};

export default WizardTune;

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
import { tuner_status, run_tuner, kill_tuner } from "../../util/api";
import { TunerStatus, TunerTrial } from "../../util/types";
import FileSelector from "../FileSelector";

const StyledTableCell = styled(TableCell)(({ theme }) => ({
    [`&.${tableCellClasses.head}`]: {
        backgroundColor: theme.palette.primary.main,
        color: theme.palette.common.white,
    },
    [`&.${tableCellClasses.body}`]: {
        fontSize: 14,
    },
}));

const TunerTable = ({ rows }: { rows: TunerTrial[] }) => {
    if (!rows || rows.length === 0) {
        return <Typography>No tuning trials available yet.</Typography>;
    }

    return (
        <TableContainer component={Paper}>
            <Table sx={{ minWidth: 650 }} aria-label="tuner trials table">
                <TableHead sx={{ backgroundColor: "primary.main" }}>
                    <TableRow>
                        <StyledTableCell>Trial ID</StyledTableCell>
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
                    {rows.map((row) => (
                        <TableRow key={row.id} sx={{ "&:last-child td, &:last-child th": { border: 0 } }}>
                            <StyledTableCell component="th" scope="row">
                                {row.id}
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

const TunerView = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;

    const [loading, setLoading] = useState(false);
    const [tunerUp, setTunerUp] = useState(false);
    const [tunerStatus, setTunerStatus] = useState<TunerStatus | null>(null);

    const getTuner = async () => {
        const { data, error } = await tuner_status(experiment.id);
        setErrorMessage(error || "");
        setTunerUp(data?.message === "up");
        setTunerStatus(data?.status || {});
    };

    const runTuner = async () => {
        const { error } = await run_tuner(experiment.id);
        setErrorMessage(error || "");
        getTuner();
    };

    const killTuner = async () => {
        const { error } = await kill_tuner(experiment.id);
        setErrorMessage(error || "");
        getTuner();
    };

    useEffect(() => {
        setLoading(true);
        getTuner().finally(() => setLoading(false));

        let intervalId: number | null = null;

        // refresh tuner status every 5 seconds if the tuner is up
        if (tunerUp) {
            intervalId = window.setInterval(() => {
                console.log("Refreshing tuner status...");
                getTuner();
            }, 5000);
        }

        return () => {
            if (intervalId !== null) {
                console.log("Clearing tuner status interval.");
                window.clearInterval(intervalId);
            }
        };
    }, [tunerUp]);

    return (
        <>
            {(loading && <CircularProgress />) || (
                <Stack spacing={2} direction="column">
                    {(tunerUp && (
                        <>
                            <Typography variant="h5">Tuner running 🚀</Typography>
                            <Button variant="contained" color="error" onClick={killTuner}>
                                Kill tuner 🔪
                            </Button>
                            <TunerTable rows={tunerStatus?.trials || []} />
                        </>
                    )) || (
                        <>
                            <Typography variant="h5">Tuner isn't running 💔</Typography>
                            <Button variant="contained" color="primary" onClick={runTuner}>
                                Run tuner
                            </Button>
                        </>
                    )}
                </Stack>
            )}
        </>
    );
};

const WizardTune = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tunerJobs, setTunerJobs] = useState<Record<string, any>>({});

    const handleChange = (event: React.SyntheticEvent, newValue: string) => {
        setSelectedTpr(newValue);
    };

    const newTpr = (newSelectedTpr: string) => {
        const tprFile = newSelectedTpr.split("/").pop() || newSelectedTpr;
        setSelectedTpr(tprFile);

        if (tunerJobs[tprFile])
            return; // If the TPR file is already getting tuned, do nothing

        setTunerJobs((prev) => ({
            ...prev,
            [tprFile]: {
                tuner_run_id: `${experiment.id}-${tprFile}`,
                trials: [],
            },
        }));
    }


    return (
        <>
            <Tabs
                value={selectedTpr}
                onChange={handleChange}
                variant="scrollable"
                scrollButtons="auto"
            >
                {Object.keys(tunerJobs).map((tprFile) => (
                    <Tab label={tprFile} value={tprFile} />
                ))}

                <FileSelector experimentId={experiment.id} extension="tpr" onFileSelected={newTpr} width={300} />
            </Tabs>

            {selectedTpr && (
                <Box sx={{ mt: 2 }}>
                    <Typography variant="h6">Selected TPR: {selectedTpr}</Typography>
                    <Typography variant="body1">
                        Tuner Run ID: {tunerJobs[selectedTpr]?.tuner_run_id || "N/A"}
                    </Typography>
                    <TunerView experiment={experiment} setExperiment={props.setExperiment} setErrorMessage={setErrorMessage} />
                </Box>
            )}
        </>
    );
};

export default WizardTune;

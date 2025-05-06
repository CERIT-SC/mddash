import { useEffect, useState } from "react";
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
} from "@mui/material";
import { tableCellClasses } from "@mui/material/TableCell";
import { styled } from "@mui/material/styles";

import { WizardStepperProps } from "./Stepper";
import { tuner_status, run_tuner, kill_tuner } from "../../util/api";
import { TunerStatus, TunerTrial } from "../../util/types";

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

const WizardTune = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;
    const [loading, setLoading] = useState(false);
    const [tunerUp, setTunerUp] = useState(false);
    const [tunerStatus, setTunerStatus] = useState<TunerStatus | null>(null);

    console.log(experiment);
    console.log(setErrorMessage);

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
        <Box sx={{ p: 4, display: "flex", flexDirection: "column", alignItems: "center" }}>
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
        </Box>
    );
};

export default WizardTune;

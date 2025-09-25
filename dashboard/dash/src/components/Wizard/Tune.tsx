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
    Radio,
} from "@mui/material";
import { Delete, PlayArrow, Cancel, Pause } from "@mui/icons-material";
import { tableCellClasses } from "@mui/material/TableCell";
import { styled } from "@mui/material/styles";

import { WizardStepProps } from "./Stepper";
import { tuner_status, tuner_statuses, run_tuner, stop_tuner, delete_tuner } from "../../util/api";
import { JobStatus, TunerJob, TunerTrial } from "../../util/types";
import FileSelector from "../FileSelector";
import ConfirmDialog from "../ConfirmDialog";
import { StartForm } from "./Run";

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
    selectedTrial: TunerTrial | null;
    setSelectedTrial: (trial: TunerTrial | null) => void;
}

const TunerTable = (props: TunerTableProps) => {
    const { rows, selectedTrial, setSelectedTrial } = props;

    const [confirmChoiceDialog, setConfirmChoiceDialog] = useState(false);

    if (!rows || rows.length === 0) {
        return <Typography variant="body1">No tuning trials available yet...</Typography>;
    }

    return (
        <>
            <TableContainer component={Paper}>
                <Table sx={{ minWidth: 650 }} aria-label="tuner trials table">
                    <TableHead sx={{ backgroundColor: "primary.main" }}>
                        <TableRow>
                            <StyledTableCell>Select</StyledTableCell>
                            <StyledTableCell>Status</StyledTableCell>
                            <Tooltip title="Measured performance (ns/day)">
                                <StyledTableCell align="right">Performance</StyledTableCell>
                            </Tooltip>
                            <Tooltip title="Device type for PME calculations">
                                <StyledTableCell align="right">PME</StyledTableCell>
                            </Tooltip>
                            <Tooltip title="Device type for non-bonded interactions">
                                <StyledTableCell align="right">NB</StyledTableCell>
                            </Tooltip>
                            <Tooltip title="Number of MPI processes">
                                <StyledTableCell align="right">NP</StyledTableCell>
                            </Tooltip>
                            <Tooltip title="Number of OpenMP threads per MPI rank to start">
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
                            .map((row, idx) => (
                                <TableRow key={row.id} sx={{ "&:last-child td, &:last-child th": { border: 0 } }}>
                                    <StyledTableCell>
                                        <Radio
                                            checked={selectedTrial?.id === row.id}
                                            onClick={() => {
                                                if (selectedTrial?.id === row.id) {
                                                    setSelectedTrial(null);
                                                    return;
                                                }
                                                if (idx !== 0 || row.performance === null) setConfirmChoiceDialog(true);
                                                setSelectedTrial(row);
                                            }}
                                            name="selectedTrial"
                                            sx={{
                                                color:
                                                    idx === 0 && row.performance !== null ? "primary.main" : "default",
                                            }}
                                        />
                                    </StyledTableCell>
                                    <StyledTableCell
                                        sx={{
                                            color: (theme) =>
                                                theme.palette[JobStatus.getColor(row.status as JobStatus)].main,
                                        }}
                                    >
                                        {row.status}
                                    </StyledTableCell>
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
            <ConfirmDialog
                open={confirmChoiceDialog}
                setOpen={setConfirmChoiceDialog}
                onCancel={() => setSelectedTrial(null)}
                message="The selected trial doesn't have the optimal performance. Are you sure you want to proceed with these parameters?"
                confirmColor="warning"
            />
        </>
    );
};

interface TunerViewProps extends WizardStepProps {
    tprName: string;
    cancelJob: (tprName: string) => void;
    stopJob: (tprName: string) => void;
    deleteJob: (tprName: string) => void;
}

const TunerView = (props: TunerViewProps) => {
    const { experiment, tprName, setErrorMessage, stopJob, deleteJob, cancelJob, nextStep, changeStep } = props;

    const [loading, setLoading] = useState(false);
    const [tunerStarted, setTunerStarted] = useState(false);
    const [tunerStopped, setTunerStopped] = useState(false);
    const [tuner, setTuner] = useState<TunerJob | null>(null);
    const [selectedTrial, setSelectedTrial] = useState<TunerTrial | null>(null);

    const [confirmStopDialog, setConfirmStopDialog] = useState(false);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchStatus = async (showError: boolean) => {
        const { data, error } = await tuner_status(experiment.id, tprName);
        if (showError && error) setErrorMessage(error);
        setTuner(data || null);
        setTunerStarted(!!data?.trials);
        setTunerStopped(data?.is_stopped || false);

        // Maintain selected trial after data refresh
        if (selectedTrial && data?.trials) {
            const updatedSelectedTrial = data.trials.find((trial) => trial.id === selectedTrial.id);
            if (updatedSelectedTrial) {
                setSelectedTrial(updatedSelectedTrial);
            } else {
                // Trial no longer exists, clear selection
                setSelectedTrial(null);
            }
        }
    };

    const runTuner = async () => {
        const { error } = await run_tuner(experiment.id, tprName);
        setErrorMessage(error || "");
        fetchStatus(true);
    };

    const goToRunStep = async (_: boolean) => {
        if (experiment.step < 2) nextStep();
        else changeStep(2);
    };

    useEffect(() => {
        setLoading(true);
        fetchStatus(false).finally(() => setLoading(false));

        let intervalId: number | null = null;

        // refresh tuner status every 5 seconds if the tuner is up and running
        if (tunerStarted && !tunerStopped) {
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
    }, [tprName, experiment.id, tunerStarted, tunerStopped]);

    return (
        <>
            {(loading && (
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                    <CircularProgress />
                </Box>
            )) || (
                <>
                    {(tunerStarted && (
                        <Stack direction="column" spacing={2}>
                            <TunerTable
                                rows={tuner?.trials || []}
                                selectedTrial={selectedTrial}
                                setSelectedTrial={setSelectedTrial}
                            />

                            <Stack direction="row" spacing={2} justifyContent="flex-end">
                                {tunerStopped || (
                                    <Button
                                        variant="contained"
                                        color="warning"
                                        startIcon={<Pause />}
                                        onClick={() => setConfirmStopDialog(true)}
                                    >
                                        Stop
                                    </Button>
                                )}
                                <Button
                                    variant="contained"
                                    color="error"
                                    startIcon={<Delete />}
                                    onClick={() => setConfirmDeleteDialog(true)}
                                >
                                    Delete
                                </Button>
                            </Stack>

                            {selectedTrial && (
                                <StartForm
                                    fetchStatus={goToRunStep}
                                    np={selectedTrial.np}
                                    ntomp={selectedTrial.ntomp}
                                    nb={selectedTrial.nb}
                                    pme={selectedTrial.pme}
                                    {...props}
                                />
                            )}
                        </Stack>
                    )) || (
                        <Stack direction="column" spacing={1} alignItems="center">
                            <Typography variant="h4">Tuner not running.</Typography>
                            <Button
                                variant="contained"
                                color="primary"
                                startIcon={<PlayArrow />}
                                onClick={runTuner}
                                sx={{ width: 200 }}
                            >
                                Start tune job
                            </Button>
                            <Button
                                variant="contained"
                                color="error"
                                startIcon={<Cancel />}
                                onClick={() => cancelJob(tprName)}
                                sx={{ width: 200 }}
                            >
                                Cancel
                            </Button>
                        </Stack>
                    )}
                </>
            )}

            <ConfirmDialog
                open={confirmStopDialog}
                setOpen={setConfirmStopDialog}
                confirmColor="warning"
                onConfirm={() => stopJob(tprName)}
                message="Are you sure you want to stop the tuning job? You cannot resume it, but data will be preserved."
            />
            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(tprName)}
                message="Are you sure you want to delete this tuning job? The data will be lost."
            />
        </>
    );
};

const WizardTune = (props: WizardStepProps) => {
    const { experiment, setErrorMessage, nextStep, changeStep } = props;

    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [tprFiles, setTprFiles] = useState<string[]>([]);
    const [confirmSkipTuningDialog, setConfirmSkipTuningDialog] = useState(false);

    const handleChange = (_: React.SyntheticEvent, newValue: string) => {
        setSelectedTpr(newValue);
    };

    const newTpr = (newSelectedTpr: string) => {
        if (!newSelectedTpr) return;

        const tprFile = newSelectedTpr.split("/").pop() || newSelectedTpr;
        setSelectedTpr(tprFile);

        if (!tprFiles.includes(tprFile)) setTprFiles((prev) => [...prev, tprFile]);
    };

    const fetchTunerJobs = async () => {
        const { data, error } = await tuner_statuses(experiment.id);
        setErrorMessage(error || "");
        const jobs = data || [];

        if (jobs.length === 0) setSelectedTpr(null);

        const jobTprNames = jobs.map((job) => job.tpr_name);
        setTprFiles(jobTprNames);
    };

    const cancelJob = async (tprName: string) => {
        setSelectedTpr(null);
        setTprFiles((prev) => prev.filter((tpr) => tpr !== tprName));
    };

    const stopJob = async (tprName: string) => {
        const { error } = await stop_tuner(experiment.id, tprName);
        setErrorMessage(error || "");
        fetchTunerJobs();
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
            setTprFiles([]);
            setSelectedTpr(null);
        };
    }, [experiment.id, setErrorMessage]);

    return (
        <>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Stack direction="row" spacing={2} alignItems="center">
                    {tprFiles.length > 0 && (
                        <Tabs
                            value={selectedTpr || false}
                            onChange={handleChange}
                            variant="scrollable"
                            scrollButtons="auto"
                        >
                            {tprFiles.map((tprFile) => (
                                <Tab key={tprFile} value={tprFile} label={tprFile} />
                            ))}
                        </Tabs>
                    )}

                    <FileSelector
                        experimentId={experiment.id}
                        ext="tpr"
                        title="Select TPR file"
                        onFileSelected={newTpr}
                        width={300}
                    />
                </Stack>

                {tprFiles.length === 0 && experiment.step < 2 && (
                    <Button variant="contained" color="error" onClick={() => setConfirmSkipTuningDialog(true)}>
                        Skip tuning
                    </Button>
                )}
            </Stack>

            {selectedTpr && (
                <Box sx={{ mt: 2 }}>
                    <TunerView
                        tprName={selectedTpr}
                        cancelJob={cancelJob}
                        stopJob={stopJob}
                        deleteJob={deleteJob}
                        {...props}
                    />
                </Box>
            )}

            <ConfirmDialog
                open={confirmSkipTuningDialog}
                setOpen={setConfirmSkipTuningDialog}
                onConfirm={() => {
                    if (experiment.step < 2) nextStep();
                    else changeStep(2);
                }}
                message="Are you sure you want to skip the tuning step? You can always come back to it later."
            />
        </>
    );
};

export default WizardTune;

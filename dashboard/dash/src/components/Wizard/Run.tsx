import { useState, useEffect, useRef, useMemo, useCallback } from "react";

import {
    Box,
    Stack,
    Tabs,
    Tab,
    Typography,
    CircularProgress,
    Chip,
    Grid2 as Grid,
    Button,
    FormControl,
    MenuItem,
    InputLabel,
    Select,
    TextField,
    LinearProgress,
} from "@mui/material";

import { WizardStepProps } from "./Stepper";
import FileSelector from "../FileSelector";
import { GromacsJob } from "../../util/types";
import { submit_gmx, delete_gmx, gmx_status, gmx_statuses, gmx_logs } from "../../util/api";
import LogsView from "../LogsView";
import ConfirmDialog from "../ConfirmDialog";

const MDRUN_ARGUMENTS = [
    { key: "xvg", type: "select", options: ["xmgrace", "xmgr", "none"], description: "xvg plot formatting" },
    { key: "dd", type: "text", description: "Domain decomposition grid, 0 is optimize" },
    { key: "ddorder", type: "select", options: ["interleave", "pp_pme", "cartesian"], description: "DD rank order" },
    { key: "npme", type: "number", description: "Number of PME ranks, -1 is guess" },
    { key: "nt", type: "number", description: "Total threads to start (0 is guess)" },
    { key: "ntmpi", type: "number", description: "Number of thread-MPI ranks (0 is guess)" },
    { key: "ntomp_pme", type: "number", description: "OpenMP threads per MPI rank for PME (0 is -ntomp)" },
    { key: "pin", type: "select", options: ["auto", "on", "off"], description: "Set thread affinities" },
    { key: "pinoffset", type: "number", description: "Lowest logical core for first thread pin" },
    {
        key: "pinstride",
        type: "number",
        description: "Pinning distance in logical cores, 0 minimizes threads per physical core",
    },
    { key: "gpu_id", type: "text", description: "List of unique GPU device IDs" },
    { key: "gputasks", type: "text", description: "GPU device IDs mapping tasks to devices (PP and PME)" },
    { key: "ddcheck", type: "boolean", description: "Check all bonded interactions with DD" },
    { key: "rdd", type: "number", description: "Max distance for bonded interactions with DD (nm), 0 auto-determines" },
    { key: "rcon", type: "number", description: "Max distance for P-LINCS (nm), 0 estimates" },
    { key: "dlb", type: "select", options: ["auto", "no", "yes"], description: "Dynamic load balancing with DD" },
    {
        key: "dds",
        type: "number",
        description: "Fraction (0,1) to increase initial DD cell size for load balancing margin",
    },
    { key: "nstlist", type: "number", description: "Set nstlist with Verlet buffer tolerance (0 is guess)" },
    { key: "tunepme", type: "boolean", description: "Optimize PME load between PP/PME ranks or GPU/CPU" },
    { key: "pmefft", type: "select", options: ["auto", "cpu", "gpu"], description: "Perform PME FFT calculations on" },
    { key: "bonded", type: "select", options: ["auto", "cpu", "gpu"], description: "Perform bonded calculations on" },
    {
        key: "update",
        type: "select",
        options: ["auto", "cpu", "gpu"],
        description: "Perform update and constraints on",
    },
    { key: "v", type: "boolean", description: "Verbose output" },
    { key: "pforce", type: "number", description: "Print forces larger than this (kJ/mol nm)" },
    {
        key: "reprod",
        type: "boolean",
        description: "Avoid optimizations affecting binary reproducibility (reduces performance)",
    },
    { key: "cpt", type: "number", description: "Checkpoint interval (minutes)" },
    { key: "cpnum", type: "boolean", description: "Keep and number checkpoint files" },
    { key: "append", type: "boolean", description: "Append to previous output files when continuing from checkpoint" },
    { key: "nsteps", type: "number", description: "Run this many steps (-1 infinite, -2 use mdp option)" },
    { key: "maxh", type: "number", description: "Terminate after 0.99 × this time (hours)" },
    { key: "replex", type: "number", description: "Replica exchange period (steps)" },
    {
        key: "nex",
        type: "number",
        description: "Random exchanges per interval (N^3 suggested), 0 for neighbor exchange",
    },
    { key: "reseed", type: "number", description: "Replica exchange seed, -1 generates seed" },
];

interface ManualStartFormProps extends WizardStepProps {
    tprName: string;
    fetchStatus: (showError: boolean) => Promise<void>;
    np?: number;
    ntomp?: number;
    pme?: "cpu" | "gpu" | "auto";
    nb?: "cpu" | "gpu" | "auto";
}

export const StartForm = (props: ManualStartFormProps) => {
    const { experiment, tprName, setErrorMessage, fetchStatus, np, ntomp, nb, pme } = props;

    const [selectedArgument, setSelectedArgument] = useState("");
    const [argumentValue, setArgumentValue] = useState("");
    const [addedArguments, setAddedArguments] = useState<Array<{ key: string; value: any; description: string }>>([]);

    const formRef = useRef<HTMLFormElement>(null);

    const handleAddArgument = () => {
        if (!selectedArgument) return;
        const selectedArgConfig = MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument);
        if (!selectedArgConfig) return;
        if (selectedArgConfig.type !== "boolean" && argumentValue.trim() === "") return;

        // Check if argument already exists
        if (addedArguments.some((arg) => arg.key === selectedArgument)) {
            setErrorMessage("Argument already added");
            return;
        }

        setAddedArguments((prev) => [
            ...prev,
            {
                key: selectedArgument,
                value: argumentValue.trim(),
                description: selectedArgConfig.description,
            },
        ]);

        setSelectedArgument("");
        setArgumentValue("");
    };

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault(); // Prevent page reload

        const formData = new FormData(formRef.current!);
        formData.append("extra_args", addedArguments.map((arg) => `-${arg.key} ${arg.value}`).join(" "));

        await runSimulation(formData);
        await fetchStatus(true);
    };

    const runSimulation = async (formData: FormData) => {
        const { error } = await submit_gmx(experiment.id, tprName, formData);
        if (error) {
            setErrorMessage(error);
            return;
        }
    };

    const handleDeleteArgument = (keyToDelete: string) => {
        setAddedArguments((prev) => prev.filter((arg) => arg.key !== keyToDelete));
    };

    return (
        <Box>
            <Typography variant="h6" color="text.secondary" sx={{ mb: 2 }}>
                Start simulation
            </Typography>

            <Grid container spacing={2} ref={formRef} component="form" onSubmit={handleSubmit}>
                {/* Hidden inputs for disabled fields to ensure their values are included in FormData */}
                {!!np && <input type="hidden" name="np" value={np} />}
                {!!ntomp && <input type="hidden" name="ntomp" value={ntomp} />}
                {!!nb && <input type="hidden" name="nb" value={nb} />}
                {!!pme && <input type="hidden" name="pme" value={pme} />}

                <Grid size={6}>
                    <TextField
                        name="np"
                        type="number"
                        label="Number of MPI processes (np)"
                        slotProps={{
                            htmlInput: {
                                min: 1,
                                step: 1,
                            },
                        }}
                        required
                        fullWidth
                        defaultValue={np || ""}
                        disabled={!!np}
                    />
                </Grid>

                <Grid size={6}>
                    <TextField
                        name="ntomp"
                        type="number"
                        label="Number of OpenMP threads per MPI rank to start (-ntomp)"
                        slotProps={{
                            htmlInput: {
                                min: 0, // 0 makes mdrun guess the value
                                step: 1,
                            },
                        }}
                        required
                        fullWidth
                        defaultValue={ntomp || ""}
                        disabled={!!ntomp}
                    />
                </Grid>

                <Grid size={6}>
                    <FormControl fullWidth required>
                        <InputLabel id="nb-device-selector">Device type for non-bonded interactions (-nb)</InputLabel>
                        <Select
                            name="nb"
                            labelId="nb-device-selector"
                            label={"Device type for non-bonded interactions (-nb)"}
                            defaultValue={nb || ""}
                            disabled={!!nb}
                        >
                            <MenuItem value="cpu">CPU</MenuItem>
                            <MenuItem value="gpu">GPU</MenuItem>
                            <MenuItem value="auto">Auto</MenuItem>
                        </Select>
                    </FormControl>
                </Grid>

                <Grid size={6}>
                    <FormControl fullWidth required>
                        <InputLabel id="pme-device-selector">Device type for PME calculations (-pme)</InputLabel>
                        <Select
                            name="pme"
                            labelId="pme-device-selector"
                            label={"Device type for PME calculations (-pme)"}
                            defaultValue={pme || ""}
                            disabled={!!pme}
                        >
                            <MenuItem value="cpu">CPU</MenuItem>
                            <MenuItem value="gpu">GPU</MenuItem>
                            <MenuItem value="auto">Auto</MenuItem>
                        </Select>
                    </FormControl>
                </Grid>

                <Grid size={12}>
                    <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                        Additional mdrun arguments
                    </Typography>

                    <Stack spacing={2}>
                        <Stack direction="row" spacing={2} alignItems="center">
                            <FormControl sx={{ minWidth: "50%" }}>
                                <InputLabel id="mdrun-args-selector">Select argument</InputLabel>
                                <Select
                                    labelId="mdrun-args-selector"
                                    label="Select argument"
                                    value={selectedArgument}
                                    onChange={(e) => setSelectedArgument(e.target.value)}
                                >
                                    {MDRUN_ARGUMENTS.filter(
                                        (arg) => !addedArguments.some((added) => added.key === arg.key)
                                    ).map((arg) => (
                                        <MenuItem key={arg.key} value={arg.key}>
                                            -{arg.key} - {arg.description}
                                        </MenuItem>
                                    ))}
                                </Select>
                            </FormControl>

                            {MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument)?.type === "select" ? (
                                <FormControl sx={{ flexGrow: 1 }}>
                                    <InputLabel>Value</InputLabel>
                                    <Select
                                        label="Value"
                                        value={argumentValue}
                                        onChange={(e) => setArgumentValue(e.target.value)}
                                    >
                                        {MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument)?.options?.map(
                                            (option) => (
                                                <MenuItem key={option} value={option}>
                                                    {option}
                                                </MenuItem>
                                            )
                                        )}
                                    </Select>
                                </FormControl>
                            ) : MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument)?.type === "boolean" ? (
                                <Typography
                                    variant="body2"
                                    color="text.secondary"
                                    sx={{ flexGrow: 1, alignSelf: "center" }}
                                >
                                    Boolean flag (no value required)
                                </Typography>
                            ) : (
                                <TextField
                                    label="Value"
                                    placeholder="Enter value"
                                    value={argumentValue}
                                    type={MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument)?.type || "text"}
                                    onChange={(e) => setArgumentValue(e.target.value)}
                                    sx={{ flexGrow: 1 }}
                                />
                            )}

                            <Button
                                variant="contained"
                                onClick={handleAddArgument}
                                disabled={
                                    !selectedArgument ||
                                    (MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument)?.type !== "boolean" &&
                                        !argumentValue.trim())
                                }
                            >
                                Add
                            </Button>
                        </Stack>

                        {/* List of added arguments */}
                        <Box>
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                                Added arguments:
                            </Typography>
                            <Stack direction="row" spacing={1} flexWrap="wrap">
                                {addedArguments.length === 0 ? (
                                    <Typography variant="body2" color="text.disabled">
                                        No arguments added
                                    </Typography>
                                ) : (
                                    addedArguments.map((arg) => (
                                        <Chip
                                            key={arg.key}
                                            label={`-${arg.key} ${arg.value}`}
                                            onDelete={() => handleDeleteArgument(arg.key)}
                                            variant="outlined"
                                        />
                                    ))
                                )}
                            </Stack>
                        </Box>
                    </Stack>
                </Grid>

                <Grid size={12} sx={{ mt: 2 }}>
                    <Button type="submit" variant="contained" color="primary">
                        Submit
                    </Button>
                </Grid>
            </Grid>
        </Box>
    );
};

interface RunViewProps extends WizardStepProps {
    tprName: string;
    deleteJob: (tprName: string) => void;
}

const RunView = (props: RunViewProps) => {
    const { experiment, tprName, deleteJob, setErrorMessage } = props;

    const [loading, setLoading] = useState(false);
    const [jobRunning, setJobRunning] = useState(false);
    const [jobStatus, setJobStatus] = useState<GromacsJob | null>(null);
    const [logType, setLogType] = useState<"gmx" | "stdout" | "stderr" | null>(null);
    const [confirmDeleteDialog, setConfirmDeleteDialog] = useState(false);

    const fetchStatus = async (showError: boolean) => {
        const { data, error } = await gmx_status(experiment.id, tprName);
        if (showError && error) setErrorMessage(error);
        setJobStatus(data || null);
        setJobRunning(!!data);
    };

    // initial fetch
    useEffect(() => {
        setLoading(true);
        setLogType(null);
        fetchStatus(false).finally(() => setLoading(false));
    }, [tprName, experiment.id]);

    // polling for job status
    useEffect(() => {
        let intervalId: number | null = null;

        if (jobStatus?.status === "PENDING" || jobStatus?.status === "RUNNING") {
            intervalId = window.setInterval(() => {
                fetchStatus(true);
            }, 5000);
        }

        return () => {
            if (intervalId !== null) {
                clearInterval(intervalId);
            }
        };
    }, [jobStatus?.status]);

    const getStatusColor = (status: string) => {
        switch (status) {
            case "RUNNING":
                return "success";
            case "PENDING":
                return "warning";
            case "TERMINATED":
                return "info";
            case "ERROR":
                return "error";
            default:
                return "primary";
        }
    };

    const getLogs = useCallback(async () => {
        if (!logType) return "No log type selected";

        const { data, error } = await gmx_logs(experiment.id, tprName, logType, 100);
        setErrorMessage(error || "");
        return data || "";
    }, [experiment.id, tprName, logType, setErrorMessage]);

    const statusDisplay = useMemo(() => {
        if (!jobStatus) return null;

        return (
            <Stack spacing={2} alignItems="flex-start">
                <Typography variant="subtitle2" color="text.secondary">
                    Status
                </Typography>
                <Chip label={jobStatus.status} color={getStatusColor(jobStatus.status)} />

                {jobStatus.status === "RUNNING" && jobStatus.nsteps !== null && jobStatus.nsteps_done !== null && (
                    <>
                        <Typography variant="subtitle2" color="text.secondary">
                            Progress
                        </Typography>
                        <Box sx={{ width: "100%", minWidth: 300 }}>
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                                <Box sx={{ width: "100%", mr: 1 }}>
                                    <LinearProgress
                                        variant="determinate"
                                        value={(jobStatus.nsteps_done / jobStatus.nsteps) * 100}
                                    />
                                </Box>
                                <Box sx={{ minWidth: 35 }}>
                                    <Typography variant="body2" color="text.secondary">
                                        {`${((jobStatus.nsteps_done / jobStatus.nsteps) * 100).toFixed(1)}%`}
                                    </Typography>
                                </Box>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                                {`${jobStatus.nsteps_done.toLocaleString()} / ${jobStatus.nsteps.toLocaleString()} steps`}
                            </Typography>
                        </Box>
                    </>
                )}

                {jobStatus.performance && (
                    <>
                        <Typography variant="subtitle2" color="text.secondary">
                            Performance
                        </Typography>
                        <Typography variant="body2">{`${jobStatus.performance.toFixed(2)} ns/day`}</Typography>
                    </>
                )}

                <Typography variant="subtitle2" color="text.secondary">
                    Processes
                </Typography>
                <Typography variant="body2">
                    {jobStatus.np} × {jobStatus.ntomp} threads
                </Typography>

                <Typography variant="subtitle2" color="text.secondary">
                    PME / NB
                </Typography>
                <Typography variant="body2">
                    {jobStatus.pme} / {jobStatus.nb}
                </Typography>

                {jobStatus.extra_args && (
                    <>
                        <Typography variant="subtitle2" color="text.secondary">
                            Extra Arguments
                        </Typography>
                        <Typography variant="body2">{jobStatus.extra_args}</Typography>
                    </>
                )}
            </Stack>
        );
    }, [
        jobStatus?.status,
        jobStatus?.np,
        jobStatus?.ntomp,
        jobStatus?.pme,
        jobStatus?.nb,
        jobStatus?.extra_args,
        jobStatus?.nsteps,
        jobStatus?.nsteps_done,
        jobStatus?.performance,
    ]);

    return (
        <>
            {(loading && (
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                    <CircularProgress />
                </Box>
            )) || (
                <Box sx={{ mt: 2 }}>
                    {jobRunning ? (
                        <Stack spacing={2} alignItems="flex-start">
                            {statusDisplay}

                            <Button
                                variant="contained"
                                color="error"
                                onClick={() => {
                                    setConfirmDeleteDialog(true);
                                }}
                            >
                                Delete Job
                            </Button>

                            <Typography variant="subtitle2" color="text.secondary">
                                Logs
                            </Typography>

                            <FormControl sx={{ minWidth: 200 }}>
                                <InputLabel id="log-type-selector">Log Type</InputLabel>
                                <Select
                                    labelId="log-type-selector"
                                    label="Log Type"
                                    value={logType || ""}
                                    onChange={(e) =>
                                        setLogType((e.target.value as "gmx" | "stdout" | "stderr" | null) || null)
                                    }
                                >
                                    <MenuItem value="">
                                        <em>None</em>
                                    </MenuItem>
                                    <MenuItem value="gmx">Gromacs Log</MenuItem>
                                    <MenuItem value="stdout">Standard Output</MenuItem>
                                    <MenuItem value="stderr">Standard Error</MenuItem>
                                </Select>
                            </FormControl>

                            {logType && (
                                <LogsView
                                    getLogs={getLogs}
                                    refreshInterval={
                                        jobStatus?.status == "PENDING" || jobStatus?.status == "RUNNING"
                                            ? 5000
                                            : undefined
                                    }
                                />
                            )}
                        </Stack>
                    ) : (
                        <StartForm fetchStatus={fetchStatus} {...props} />
                    )}
                </Box>
            )}
            <ConfirmDialog
                open={confirmDeleteDialog}
                setOpen={setConfirmDeleteDialog}
                onConfirm={() => deleteJob(tprName)}
                message="Are you sure you want to delete this Gromacs job? The data will be lost."
            />
        </>
    );
};

const WizardRun = (props: WizardStepProps) => {
    const { experiment, setErrorMessage } = props;
    const [selectedTpr, setSelectedTpr] = useState<string | null>(null);
    const [gromacsJobs, setGromacsJobs] = useState<Record<string, GromacsJob | null>>({});

    const handleChange = (_: React.SyntheticEvent, newValue: string) => {
        setSelectedTpr(newValue);
    };

    const fetchGromacsJobs = async () => {
        const { data, error } = await gmx_statuses(experiment.id);
        setErrorMessage(error || "");
        setGromacsJobs(data || {});
    };

    const newTpr = (newSelectedTpr: string) => {
        if (!newSelectedTpr) return;

        const tprFile = newSelectedTpr.split("/").pop() || newSelectedTpr;
        setSelectedTpr(tprFile);

        if (gromacsJobs[tprFile]) return; // If the TPR file is already getting simulated, do nothing

        setGromacsJobs((prev) => ({
            ...prev,
            [tprFile]: null,
        }));
    };

    const deleteJob = async (tprName: string) => {
        const { error } = await delete_gmx(experiment.id, tprName);
        setErrorMessage(error || "");
        setSelectedTpr(null);
        fetchGromacsJobs();
    };

    useEffect(() => {
        fetchGromacsJobs();

        return () => {
            console.log("Cleaning up tuner jobs.");
            setGromacsJobs({});
            setSelectedTpr(null);
        };
    }, [experiment.id, setErrorMessage]);

    return (
        <>
            <Stack direction="row" spacing={2} alignItems="center">
                <Tabs value={selectedTpr || false} onChange={handleChange} variant="scrollable" scrollButtons="auto">
                    {Object.keys(gromacsJobs).map((tprFile) => (
                        <Tab label={tprFile} key={tprFile} value={tprFile} />
                    ))}
                </Tabs>

                <FileSelector
                    experimentId={experiment.id}
                    ext="tpr"
                    title="Select TPR file"
                    onFileSelected={newTpr}
                    width={300}
                />
            </Stack>

            {selectedTpr && (
                <Box sx={{ mt: 2 }}>
                    <RunView tprName={selectedTpr} deleteJob={deleteJob} {...props} />
                </Box>
            )}
        </>
    );
};

export default WizardRun;

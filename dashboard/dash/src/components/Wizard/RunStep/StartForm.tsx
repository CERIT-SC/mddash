import { useState, useRef } from "react";

import {
    Box,
    Stack,
    Typography,
    Chip,
    Grid2 as Grid,
    Button,
    FormControl,
    MenuItem,
    InputLabel,
    Select,
    TextField,
} from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { submit_gmx } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";

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
    const { experiment, tprName, fetchStatus, np, ntomp, nb, pme } = props;
    const { showError, showWarning } = useNotification();

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
            showWarning("Argument already added");
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
            showError(error);
            return;
        }
    };

    const handleDeleteArgument = (keyToDelete: string) => {
        setAddedArguments((prev) => prev.filter((arg) => arg.key !== keyToDelete));
    };

    return (
        <Box>
            <Typography variant="h3" sx={{ mb: 2 }}>
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
                    <Typography variant="subtitle1" sx={{ mb: 1 }}>
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
                            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
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

export default StartForm;

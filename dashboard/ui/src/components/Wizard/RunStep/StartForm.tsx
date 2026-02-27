import React, { useState, useMemo, useCallback } from "react";

import { Plus, Rocket, X } from "lucide-react";
import { toast } from "sonner";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { useSubmitGmx } from "@/hooks/use-gromacs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NONE_DEVICE = "__none__";

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
] as const;

interface ManualStartFormProps extends WizardStepProps {
    tprName: string;
    onStartJob: () => void;
    np?: number;
    ntomp?: number;
    pme?: "cpu" | "gpu" | "auto";
    nb?: "cpu" | "gpu" | "auto";
}

const NONE_ARG = "__none__";

export const StartForm = (props: ManualStartFormProps) => {
    const { experiment, tprName, onStartJob, np, ntomp, nb, pme } = props;

    const submitGmx = useSubmitGmx(experiment.id);

    const [selectedArgument, setSelectedArgument] = useState(NONE_ARG);
    const [argumentValue, setArgumentValue] = useState("");
    const [addedArguments, setAddedArguments] = useState<Array<{ key: string; value: string; description: string }>>(
        [],
    );

    const selectedArgConfig = useMemo(
        () => MDRUN_ARGUMENTS.find((arg) => arg.key === selectedArgument),
        [selectedArgument],
    );

    const availableArguments = useMemo(
        () => MDRUN_ARGUMENTS.filter((arg) => !addedArguments.some((added) => added.key === arg.key)),
        [addedArguments],
    );

    const isAddDisabled = useMemo(() => {
        if (!selectedArgument || selectedArgument === NONE_ARG) return true;
        if (selectedArgConfig?.type === "boolean") return false;
        return !argumentValue.trim();
    }, [selectedArgument, selectedArgConfig, argumentValue]);

    const handleSelectArgument = useCallback((value: string) => {
        setSelectedArgument(value);
        setArgumentValue("");
    }, []);

    const handleAddArgument = useCallback(() => {
        if (!selectedArgument || selectedArgument === NONE_ARG || !selectedArgConfig) return;

        if (addedArguments.some((arg) => arg.key === selectedArgument)) {
            toast.warning("Argument already added");
            return;
        }

        setAddedArguments((prev) => [
            ...prev,
            { key: selectedArgument, value: argumentValue.trim(), description: selectedArgConfig.description },
        ]);

        setSelectedArgument(NONE_ARG);
        setArgumentValue("");
    }, [selectedArgument, selectedArgConfig, argumentValue, addedArguments]);

    const handleDeleteArgument = useCallback((keyToDelete: string) => {
        setAddedArguments((prev) => prev.filter((arg) => arg.key !== keyToDelete));
    }, []);

    const handleSubmit = useCallback(
        async (event: React.FormEvent<HTMLFormElement>) => {
            event.preventDefault();

            const formData = new FormData(event.currentTarget);
            const extraArgs = addedArguments.map((arg) => `-${arg.key} ${arg.value}`).join(" ");
            formData.append("extra_args", extraArgs);

            submitGmx.mutate({ tprName, formData }, { onSuccess: () => onStartJob() });
        },
        [tprName, addedArguments, onStartJob, submitGmx],
    );

    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="text-base">Start simulation</CardTitle>
            </CardHeader>
            <CardContent>
                <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                    {/* Hidden inputs for pre-filled values */}
                    {!!np && <input type="hidden" name="np" value={np} />}
                    {!!ntomp && <input type="hidden" name="ntomp" value={ntomp} />}
                    {!!nb && <input type="hidden" name="nb" value={nb} />}
                    {!!pme && <input type="hidden" name="pme" value={pme} />}

                    <div className="grid grid-cols-2 gap-3">
                        <div className="flex flex-col gap-1">
                            <Label htmlFor="np-input">Number of MPI processes (np)</Label>
                            <Input
                                id="np-input"
                                name="np"
                                type="number"
                                min={1}
                                step={1}
                                required
                                defaultValue={np || ""}
                                disabled={!!np}
                            />
                        </div>

                        <div className="flex flex-col gap-1">
                            <Label htmlFor="ntomp-input">OpenMP threads per MPI rank (-ntomp)</Label>
                            <Input
                                id="ntomp-input"
                                name="ntomp"
                                type="number"
                                min={0}
                                step={1}
                                required
                                defaultValue={ntomp || ""}
                                disabled={!!ntomp}
                            />
                        </div>

                        <div className="flex flex-col gap-1">
                            <Label htmlFor="nb-select">Device type for non-bonded interactions (-nb)</Label>
                            <Select name="nb" defaultValue={nb || NONE_DEVICE} disabled={!!nb} required>
                                <SelectTrigger id="nb-select">
                                    <SelectValue placeholder="Select device" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value={NONE_DEVICE} disabled>
                                        <em>Select...</em>
                                    </SelectItem>
                                    <SelectItem value="cpu">CPU</SelectItem>
                                    <SelectItem value="gpu">GPU</SelectItem>
                                    <SelectItem value="auto">Auto</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="flex flex-col gap-1">
                            <Label htmlFor="pme-select">Device type for PME calculations (-pme)</Label>
                            <Select name="pme" defaultValue={pme || NONE_DEVICE} disabled={!!pme} required>
                                <SelectTrigger id="pme-select">
                                    <SelectValue placeholder="Select device" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value={NONE_DEVICE} disabled>
                                        <em>Select...</em>
                                    </SelectItem>
                                    <SelectItem value="cpu">CPU</SelectItem>
                                    <SelectItem value="gpu">GPU</SelectItem>
                                    <SelectItem value="auto">Auto</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    {/* Additional mdrun arguments */}
                    <div className="flex flex-col gap-2">
                        <Label>Additional mdrun arguments</Label>

                        <div className="flex gap-2 items-end flex-wrap">
                            <div className="flex flex-col gap-1 flex-1 min-w-48">
                                <Select value={selectedArgument} onValueChange={handleSelectArgument}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select argument" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value={NONE_ARG}>
                                            <em>Select argument</em>
                                        </SelectItem>
                                        {availableArguments.map((arg) => (
                                            <SelectItem key={arg.key} value={arg.key}>
                                                -{arg.key} — {arg.description}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            {selectedArgConfig?.type === "select" ? (
                                <div className="flex-1 min-w-32">
                                    <Select value={argumentValue} onValueChange={setArgumentValue}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Value" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {"options" in selectedArgConfig &&
                                                selectedArgConfig.options.map((opt) => (
                                                    <SelectItem key={opt} value={opt}>
                                                        {opt}
                                                    </SelectItem>
                                                ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            ) : selectedArgConfig?.type === "boolean" ? (
                                <p className="flex-1 text-sm text-muted-foreground self-center">
                                    Boolean flag (no value required)
                                </p>
                            ) : (
                                <div className="flex-1 min-w-32">
                                    <Input
                                        placeholder="Value"
                                        value={argumentValue}
                                        type={selectedArgConfig?.type === "number" ? "number" : "text"}
                                        onChange={(e) => setArgumentValue(e.target.value)}
                                    />
                                </div>
                            )}

                            <Button
                                type="button"
                                variant="default"
                                onClick={handleAddArgument}
                                disabled={isAddDisabled}
                            >
                                <Plus className="h-4 w-4 mr-1" />
                                Add
                            </Button>
                        </div>

                        <div className="flex flex-col gap-1">
                            <p className="text-xs text-muted-foreground">Added arguments:</p>
                            <div className="flex flex-wrap gap-1">
                                {addedArguments.length === 0 ? (
                                    <p className="text-xs text-muted-foreground italic">No arguments added</p>
                                ) : (
                                    addedArguments.map((arg) => (
                                        <Badge key={arg.key} variant="outline" className="gap-1">
                                            -{arg.key} {arg.value}
                                            <button
                                                type="button"
                                                onClick={() => handleDeleteArgument(arg.key)}
                                                className="ml-1 hover:text-destructive"
                                            >
                                                <X className="h-3 w-3" />
                                            </button>
                                        </Badge>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="flex justify-end mt-2">
                        <Button type="submit" disabled={submitGmx.isPending}>
                            <Rocket className="h-4 w-4 mr-1" />
                            Run
                        </Button>
                    </div>
                </form>
            </CardContent>
        </Card>
    );
};

export default StartForm;

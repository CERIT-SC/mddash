import { useState, useMemo, useCallback } from "react";

import { Loader2 } from "lucide-react";

import { JobStatus, TunerTrial, getJobStatusVariant, statusBadgeClass } from "@/util/types";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface TunerTableProps {
    rows: TunerTrial[];
    selectedTrial: TunerTrial | null;
    setSelectedTrial: (trial: TunerTrial | null) => void;
    tunerStopped?: boolean;
}

const TunerTable = (props: TunerTableProps) => {
    const { rows, selectedTrial, setSelectedTrial, tunerStopped = false } = props;

    const [confirmChoiceDialog, setConfirmChoiceDialog] = useState(false);

    const sortedRows = useMemo(() => {
        const statusRank: Record<JobStatus, number> = {
            TERMINATED: 0,
            RUNNING: 1,
            ERROR: 2,
            PENDING: 3,
            UNKNOWN: 4,
        };

        return [...rows].sort((a, b) => {
            if (a.performance === null && b.performance === null) return statusRank[a.status] - statusRank[b.status];
            if (a.performance === null) return 1;
            if (b.performance === null) return -1;
            if (a.performance !== b.performance) return b.performance - a.performance;
            return statusRank[a.status] - statusRank[b.status];
        });
    }, [rows]);

    const handleRadioClick = useCallback(
        (row: TunerTrial, isOptimal: boolean) => {
            if (selectedTrial?.id === row.id) {
                setSelectedTrial(null);
                return;
            }
            if (!isOptimal) setConfirmChoiceDialog(true);
            setSelectedTrial(row);
        },
        [selectedTrial, setSelectedTrial],
    );

    if (rows.length === 0) {
        return (
            <div className="rounded-md border p-6 flex justify-center items-center">
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                    {tunerStopped ? (
                        <span>No trials completed. The tuning job was stopped before any trials finished.</span>
                    ) : (
                        <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>Waiting for tuning trials...</span>
                        </>
                    )}
                </div>
            </div>
        );
    }

    return (
        <>
            <div className="rounded-md border overflow-hidden">
                <Table>
                    <TableHeader>
                        <TableRow className="bg-primary hover:bg-primary">
                            <TableHead className="text-primary-foreground">Select</TableHead>
                            <TableHead className="text-primary-foreground">Status</TableHead>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <TableHead className="text-primary-foreground text-right cursor-help">
                                        Performance
                                    </TableHead>
                                </TooltipTrigger>
                                <TooltipContent>Measured performance (ns/day)</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <TableHead className="text-primary-foreground text-right cursor-help">
                                        PME
                                    </TableHead>
                                </TooltipTrigger>
                                <TooltipContent>Device type for PME calculations</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <TableHead className="text-primary-foreground text-right cursor-help">NB</TableHead>
                                </TooltipTrigger>
                                <TooltipContent>Device type for non-bonded interactions</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <TableHead className="text-primary-foreground text-right cursor-help">NP</TableHead>
                                </TooltipTrigger>
                                <TooltipContent>Number of MPI processes</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <TableHead className="text-primary-foreground text-right cursor-help">
                                        NTOMP
                                    </TableHead>
                                </TooltipTrigger>
                                <TooltipContent>Number of OpenMP threads per MPI rank</TooltipContent>
                            </Tooltip>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {sortedRows.map((row, idx) => {
                            const isOptimal = idx === 0 && row.performance !== null;
                            const variant = getJobStatusVariant(row.status as JobStatus);
                            return (
                                <TableRow key={row.id}>
                                    <TableCell>
                                        <input
                                            type="radio"
                                            name="selectedTrial"
                                            checked={selectedTrial?.id === row.id}
                                            onChange={() => handleRadioClick(row, isOptimal)}
                                            onClick={() => {
                                                if (selectedTrial?.id === row.id) {
                                                    setSelectedTrial(null);
                                                }
                                            }}
                                            className={cn(
                                                "cursor-pointer",
                                                isOptimal ? "accent-primary" : "accent-muted-foreground",
                                            )}
                                        />
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant="outline" className={cn("text-xs", statusBadgeClass(variant))}>
                                            {row.status}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        {row.performance !== null ? row.performance.toFixed(2) : "N/A"}
                                    </TableCell>
                                    <TableCell className="text-right">{row.pme}</TableCell>
                                    <TableCell className="text-right">{row.nb}</TableCell>
                                    <TableCell className="text-right">{row.np}</TableCell>
                                    <TableCell className="text-right">{row.ntomp}</TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            </div>
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

export default TunerTable;

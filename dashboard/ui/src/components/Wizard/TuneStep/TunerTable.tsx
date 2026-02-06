import { useState, useMemo, useCallback } from "react";

import {
    Typography,
    Chip,
    TableContainer,
    Table,
    TableHead,
    TableRow,
    TableCell,
    TableBody,
    Paper,
    Tooltip,
    Radio,
    CircularProgress,
    Stack,
} from "@mui/material";
import { tableCellClasses } from "@mui/material/TableCell";
import { styled } from "@mui/material/styles";

import { JobStatus, TunerTrial, getJobStatusColor } from "@/util/types";
import ConfirmDialog from "@/components/ConfirmDialog";

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
            // Both performances missing -> sort by status
            if (a.performance === null && b.performance === null) return statusRank[a.status] - statusRank[b.status];

            // Treat null performance as worst
            if (a.performance === null) return 1;
            if (b.performance === null) return -1;

            // Different measured performance -> sort descending
            if (a.performance !== b.performance) return b.performance - a.performance;

            // Same performance -> fallback to status ordering
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
            <Paper variant="outlined" sx={{ p: 4, display: "flex", justifyContent: "center", alignItems: "center" }}>
                <Stack direction="row" spacing={2} alignItems="center">
                    {tunerStopped ? (
                        <Typography variant="body1" color="text.secondary">
                            No trials completed. The tuning job was stopped before any trials finished.
                        </Typography>
                    ) : (
                        <>
                            <CircularProgress size={24} />
                            <Typography variant="body1" color="text.secondary">
                                Waiting for tuning trials...
                            </Typography>
                        </>
                    )}
                </Stack>
            </Paper>
        );
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
                        {sortedRows.map((row, idx) => {
                            const isOptimal = idx === 0 && row.performance !== null;
                            return (
                                <TableRow key={row.id} sx={{ "&:last-child td, &:last-child th": { border: 0 } }}>
                                    <StyledTableCell>
                                        <Radio
                                            checked={selectedTrial?.id === row.id}
                                            onClick={() => handleRadioClick(row, isOptimal)}
                                            name="selectedTrial"
                                            sx={{ color: isOptimal ? "text.primary" : "text.disabled" }}
                                        />
                                    </StyledTableCell>
                                    <StyledTableCell>
                                        <Chip
                                            size="small"
                                            label={row.status}
                                            color={getJobStatusColor(row.status as JobStatus)}
                                        />
                                    </StyledTableCell>
                                    <StyledTableCell align="right">
                                        {row.performance !== null ? row.performance.toFixed(2) : "N/A"}
                                    </StyledTableCell>
                                    <StyledTableCell align="right">{row.pme}</StyledTableCell>
                                    <StyledTableCell align="right">{row.nb}</StyledTableCell>
                                    <StyledTableCell align="right">{row.np}</StyledTableCell>
                                    <StyledTableCell align="right">{row.ntomp}</StyledTableCell>
                                </TableRow>
                            );
                        })}
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

export default TunerTable;

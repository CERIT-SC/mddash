import { useState } from "react";

import {
    Typography,
    TableContainer,
    Table,
    TableHead,
    TableRow,
    TableCell,
    TableBody,
    Paper,
    Tooltip,
    Radio,
} from "@mui/material";
import { tableCellClasses } from "@mui/material/TableCell";
import { styled } from "@mui/material/styles";

import { JobStatus, TunerTrial } from "@/util/types";
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

export default TunerTable;

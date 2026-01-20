import { useState } from "react";

import { Stack, Paper, Typography, Button, IconButton, CircularProgress, Box } from "@mui/material";
import { Delete, Add } from "@mui/icons-material";

import FileSelector from "@/components/FileSelector";

interface TprSelectorProps {
    experimentId: string;
    title?: string;
    addTitle: string;
    tprFiles: string[];
    selectedTpr: string | null;
    loading?: boolean;
    onAddTpr: (tpr: string) => void;
    onDeleteTpr: (tpr: string) => void;
    onSelectTpr: (tpr: string) => void;
}

const TprSelector = (props: TprSelectorProps) => {
    const { experimentId, title, addTitle, tprFiles, selectedTpr, loading, onAddTpr, onDeleteTpr, onSelectTpr } = props;

    const [fileSelectorTpr, setFileSelectorTpr] = useState<string>("");

    return (
        <Paper variant="outlined" sx={{ width: 300, padding: 4 }}>
            <Stack direction="column" spacing={2}>
                {title && <Typography variant="h3">{title}</Typography>}
                <FileSelector
                    experimentId={experimentId}
                    ext="tpr"
                    title="Select TPR file"
                    onFileSelected={(filePath) => setFileSelectorTpr(filePath.split("/").pop() ?? "")}
                    ignoreFiles={tprFiles}
                />
                <Button
                    variant="contained"
                    color="primary"
                    startIcon={<Add />}
                    disabled={!fileSelectorTpr || tprFiles.includes(fileSelectorTpr)}
                    onClick={() => {
                        onAddTpr(fileSelectorTpr);
                        setFileSelectorTpr("");
                    }}
                >
                    {addTitle}
                </Button>

                <Stack direction="column" spacing={1}>
                    {loading ? (
                        <Box display="flex" justifyContent="center" py={2}>
                            <CircularProgress size={24} />
                        </Box>
                    ) : (
                        tprFiles.map((tpr) => (
                            <Stack
                                key={tpr}
                                direction="row"
                                spacing={2}
                                alignItems="center"
                                justifyContent="space-between"
                                sx={{
                                    padding: "8px 12px",
                                    cursor: "pointer",
                                    borderRadius: 1,
                                    border: 1,
                                    borderColor: selectedTpr === tpr ? "text.primary" : "divider",
                                    backgroundColor: selectedTpr === tpr ? "primary.main" : "background.paper",
                                    "&:hover": {
                                        backgroundColor: selectedTpr === tpr ? "primary.main" : "action.hover",
                                    },
                                    color: selectedTpr === tpr ? "primary.contrastText" : "text.primary",
                                    transition: "all 0.2s",
                                }}
                            >
                                <Typography
                                    variant="body1"
                                    onClick={() => {
                                        if (selectedTpr === tpr) onSelectTpr("");
                                        else onSelectTpr(tpr);
                                    }}
                                    title={tpr}
                                    sx={{
                                        flexGrow: 1,
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                        whiteSpace: "nowrap",
                                    }}
                                >
                                    {tpr}
                                </Typography>
                                <IconButton
                                    aria-label="delete"
                                    size="small"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDeleteTpr(tpr);
                                    }}
                                    sx={{
                                        color: selectedTpr === tpr ? "primary.contrastText" : "text.primary",
                                    }}
                                >
                                    <Delete fontSize="small" />
                                </IconButton>
                            </Stack>
                        ))
                    )}
                </Stack>
            </Stack>
        </Paper>
    );
};

export default TprSelector;

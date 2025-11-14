import { useState } from "react";

import { Stack, Box, Typography, Button, IconButton } from "@mui/material";
import { Delete, Add } from "@mui/icons-material";

import FileSelector from "@/components/FileSelector";

interface TprSelectorProps {
    experimentId: string;
    addTitle: string;
    tprFiles: string[];
    selectedTpr: string | null;
    onAddTpr: (tpr: string) => void;
    onDeleteTpr: (tpr: string) => void;
    onSelectTpr: (tpr: string) => void;
}

const TprSelector = (props: TprSelectorProps) => {
    const { experimentId, addTitle, tprFiles, selectedTpr, onAddTpr, onDeleteTpr, onSelectTpr } = props;

    const [fileSelectorTpr, setFileSelectorTpr] = useState<string>("");

    return (
        <Box sx={{ padding: 4, border: 2, borderColor: 'divider', borderRadius: 1, minWidth: 300 }}>
            <Stack direction="column" spacing={2}>
                <Typography variant="subtitle1">Select TPR file</Typography>
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
                    {tprFiles.map((tpr) => (
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
                                border: "1px solid",
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
                                sx={{ flexGrow: 1 }}
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
                    ))}
                </Stack>
            </Stack>
        </Box>
    );
};

export default TprSelector;

import { useState, useCallback, useEffect } from "react";
import { Box, Button, Typography, Stack, Paper, Chip, Alert, CircularProgress } from "@mui/material";
import { CloudUpload, Edit, CheckCircle, Info, Folder, Storage } from "@mui/icons-material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { publish_experiment, find_files } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";
import { formatFileSize } from "@/util/helpers";

const MDREPO_BASE_URL = "https://mdrepo.eu";

const PublishStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();
    const [loading, setLoading] = useState(false);
    const [loadingStats, setLoadingStats] = useState(true);
    const [fileCount, setFileCount] = useState(0);
    const [totalSize, setTotalSize] = useState(0);

    const isPublished = experiment.mdrepo_id !== null;

    useEffect(() => {
        const fetchFileStats = async () => {
            setLoadingStats(true);
            const { data, error } = await find_files(experiment.id);

            if (error) {
                showError(error);
                setLoadingStats(false);
                return;
            }

            if (data) {
                setFileCount(data.length);
                setTotalSize(data.reduce((sum, file) => sum + file.size, 0));
            }

            setLoadingStats(false);
        };

        fetchFileStats();
    }, [experiment.id, showError]);

    const handlePublishClick = useCallback(async () => {
        try {
            setLoading(true);

            if (isPublished) {
                window.location.href = `${MDREPO_BASE_URL}/experiments/${experiment.mdrepo_id}/edit`;
                return;
            }

            const { data, error } = await publish_experiment(experiment.id);

            if (error) {
                showError(error);
                return;
            }

            if (!data) {
                showError("Invalid response from server.");
                return;
            }

            experiment.mdrepo_id = data.id;
            window.location.href = data.links.edit_html;
        } catch (e) {
            showError("Invalid response from server.");
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, [experiment, isPublished, showError]);

    return (
        <Box sx={{ p: 4, display: "flex", justifyContent: "center" }}>
            <Paper variant="outlined" sx={{ maxWidth: 600, p: 4 }}>
                <Stack spacing={3} alignItems="center">
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Info color="action" />
                        <Typography variant="h4">Publish Experiment</Typography>
                    </Stack>

                    <Alert
                        severity={isPublished ? "success" : "info"}
                        icon={isPublished ? <CheckCircle /> : undefined}
                        sx={{ width: "100%" }}
                    >
                        <Typography variant="body2">
                            {isPublished
                                ? "This experiment is already published to MDRepo. Click below to view or edit the published version."
                                : "Publishing will upload your experiment data to MDRepo, making it publicly accessible and citable with a DOI."}
                        </Typography>
                    </Alert>

                    {loadingStats ? (
                        <Stack direction="row" spacing={1} alignItems="center">
                            <CircularProgress size={16} />
                            <Typography variant="body2" color="text.secondary">
                                Loading dataset information...
                            </Typography>
                        </Stack>
                    ) : (
                        <Stack spacing={2} sx={{ width: "100%" }}>
                            <Stack direction="row" spacing={1} alignItems="center">
                                <Folder fontSize="small" color="action" />
                                <Typography variant="subtitle2" color="text.secondary">
                                    Files:
                                </Typography>
                                <Typography variant="body1">{fileCount}</Typography>
                            </Stack>

                            <Stack direction="row" spacing={1} alignItems="center">
                                <Storage fontSize="small" color="action" />
                                <Typography variant="subtitle2" color="text.secondary">
                                    Total Size:
                                </Typography>
                                <Typography variant="body1">{formatFileSize(totalSize)}</Typography>
                            </Stack>

                            {isPublished && (
                                <Stack direction="row" spacing={1} alignItems="center">
                                    <Typography variant="subtitle2" color="text.secondary">
                                        Status:
                                    </Typography>
                                    <Chip label="Published" color="success" size="small" icon={<CheckCircle />} />
                                </Stack>
                            )}
                        </Stack>
                    )}

                    <Button
                        variant="contained"
                        color="primary"
                        size="large"
                        onClick={handlePublishClick}
                        disabled={loading}
                        startIcon={isPublished ? <Edit /> : <CloudUpload />}
                        sx={{ minWidth: 200 }}
                    >
                        {isPublished ? "View in MDRepo" : "Publish to MDRepo"}
                    </Button>

                    {!isPublished && (
                        <Typography variant="caption" color="text.secondary" textAlign="center">
                            After publishing, you'll be redirected to MDRepo to complete the metadata and finalize the
                            publication.
                        </Typography>
                    )}
                </Stack>
            </Paper>
        </Box>
    );
};

export default PublishStep;

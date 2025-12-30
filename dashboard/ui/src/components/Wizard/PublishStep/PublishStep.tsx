import { useState, useCallback, useEffect } from "react";
import { Box, Button, Typography, Stack, Paper, Chip, Alert, CircularProgress } from "@mui/material";
import { CloudUpload, Edit, CheckCircle, Info, Folder, Storage, Login } from "@mui/icons-material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { publish_experiment, find_files, get_mdrepo_status, get_mdrepo_auth_url } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import { formatFileSize } from "@/util/helpers";

const PublishStep = (props: WizardStepProps) => {
    const { experiment, setExperiment } = props;
    const { showError, showSuccess } = useNotification();
    const [loading, setLoading] = useState(false);
    const [loadingStats, setLoadingStats] = useState(true);
    const [loadingAuth, setLoadingAuth] = useState(true);
    const [fileCount, setFileCount] = useState(0);
    const [totalSize, setTotalSize] = useState(0);
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    const isPublished = experiment.mdrepo_id !== null;

    // Check for OAuth callback result in URL params
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const authSuccess = params.get("mdrepo_auth");
        const authError = params.get("mdrepo_error");

        if (authSuccess === "success") {
            showSuccess("Successfully authenticated with MDRepo!");
            // Clean up URL params
            const url = new URL(window.location.href);
            url.searchParams.delete("mdrepo_auth");
            window.history.replaceState({}, "", url.toString());
        } else if (authError) {
            showError(`MDRepo authentication failed: ${decodeURIComponent(authError)}`);
            const url = new URL(window.location.href);
            url.searchParams.delete("mdrepo_error");
            window.history.replaceState({}, "", url.toString());
        }
    }, [showSuccess, showError]);

    // Check MDRepo authentication status
    useEffect(() => {
        const checkAuth = async () => {
            setLoadingAuth(true);
            const { data, error } = await get_mdrepo_status();

            if (error) {
                console.error("Failed to check MDRepo status:", error);
                setIsAuthenticated(false);
            } else if (data) {
                setIsAuthenticated(data.authenticated);
            }
            setLoadingAuth(false);
        };

        checkAuth();
    }, []);

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

    const handleAuthClick = useCallback(() => {
        const returnUrl = window.location.href;
        window.location.href = get_mdrepo_auth_url(returnUrl);
    }, []);

    const handlePublishClick = useCallback(async () => {
        try {
            setLoading(true);

            if (isPublished) {
                window.open(experiment.mdrepo_record_url!, "_blank");
                return;
            }

            const { data, error } = await publish_experiment(experiment.id);

            if (error) {
                // Check if it's an auth error
                if (error.includes("authenticated") || error.includes("Unauthorized")) {
                    setIsAuthenticated(false);
                }
                showError(error);
                return;
            }

            if (!data) {
                showError("Invalid response from server.");
                return;
            }

            const recordUrl = data.links?.edit_html || data.links?.self_html;

            setExperiment((prev) => {
                if (!prev) return prev;
                return {
                    ...prev,
                    mdrepo_id: data.id,
                    mdrepo_record_url: recordUrl || prev.mdrepo_record_url,
                };
            });

            // Open MDRepo record in a new tab
            if (recordUrl) {
                window.open(recordUrl, "_blank");
            } else if (experiment.mdrepo_record_url) {
                window.open(experiment.mdrepo_record_url, "_blank");
            }
        } catch (e) {
            showError("Invalid response from server.");
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, [experiment, isPublished, showError, setExperiment]);

    const isLoading = loadingStats || loadingAuth;

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

                    {isLoading ? (
                        <Stack direction="row" spacing={1} alignItems="center">
                            <CircularProgress size={16} />
                            <Typography variant="body2" color="text.secondary">
                                Loading...
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

                            {!isPublished && !isAuthenticated && (
                                <Alert severity="warning" sx={{ width: "100%" }}>
                                    <Typography variant="body2">
                                        You need to authenticate with MDRepo before publishing. This is a one-time
                                        authorization using your e-INFRA CZ account.
                                    </Typography>
                                </Alert>
                            )}
                        </Stack>
                    )}

                    {!isPublished && !isAuthenticated ? (
                        <Button
                            variant="contained"
                            color="primary"
                            size="large"
                            onClick={handleAuthClick}
                            disabled={isLoading}
                            startIcon={<Login />}
                            sx={{ minWidth: 200 }}
                        >
                            Connect to MDRepo
                        </Button>
                    ) : (
                        <Button
                            variant="contained"
                            color="primary"
                            size="large"
                            onClick={handlePublishClick}
                            disabled={loading || isLoading}
                            startIcon={
                                loading ? (
                                    <CircularProgress size={20} color="inherit" />
                                ) : isPublished ? (
                                    <Edit />
                                ) : (
                                    <CloudUpload />
                                )
                            }
                            sx={{ minWidth: 200 }}
                        >
                            {isPublished ? "View in MDRepo" : "Publish to MDRepo"}
                        </Button>
                    )}

                    {!isPublished && isAuthenticated && (
                        <Typography variant="caption" color="text.secondary" textAlign="center">
                            After clicking the button, you'll be redirected to MDRepo to complete the metadata and
                            finalize the publication. Your files will be uploaded in the background.
                        </Typography>
                    )}
                </Stack>
            </Paper>
        </Box>
    );
};

export default PublishStep;

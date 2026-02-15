import { useEffect, useState, useMemo, useCallback } from "react";
import { Stack, Paper, Button, Typography, CircularProgress, Chip } from "@mui/material";

import {
    PowerSettingsNew,
    RocketLaunch,
    HelpOutline,
    Error,
    PlayArrow,
    Stop,
    Refresh,
    OpenInNew,
} from "@mui/icons-material";

import { get_notebook, spawn_notebook, delete_notebook } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import { Notebook, getPodStatusColor } from "@/util/types";

const UNKNOWN_NOTEBOOK: Notebook = {
    id: -1,
    experiment_id: "",
    token: "",
    status: "UNKNOWN",
    path: "",
};

const STATUS_CONFIG = {
    DOWN: {
        icon: PowerSettingsNew,
        color: "error" as const,
        message: "Your notebook is not running. Click the button below to start it.",
    },
    TERMINATED: {
        icon: PowerSettingsNew,
        color: "error" as const,
        message: "Your notebook is not running. Click the button below to start it.",
    },
    PENDING: {
        icon: null,
        color: null,
        message: "Your notebook is starting up. This may take a minute.",
    },
    INITIALIZING: {
        icon: null,
        color: null,
        message: "Your notebook is setting up the environment. This may take a few minutes if using Binder repository.",
    },
    TERMINATING: {
        icon: null,
        color: null,
        message: "Your notebook is shutting down. Please wait.",
    },
    RUNNING: {
        icon: RocketLaunch,
        color: "success" as const,
        message: "Your notebook is up. Click the button below to open it.",
    },
    ERROR: {
        icon: Error,
        color: "error" as const,
        message: "There was an error with your notebook. Try respawning it.",
    },
    UNKNOWN: {
        icon: HelpOutline,
        color: "disabled" as const,
        message: "Notebook status is unknown.",
    },
} as const;

interface NotebookControllerProps {
    experimentId: string;
}

const NotebookController = ({ experimentId }: NotebookControllerProps) => {
    const { showError } = useNotification();
    const [loading, setLoading] = useState(false);
    const [notebook, setNotebook] = useState<Notebook>(UNKNOWN_NOTEBOOK);
    const [displayStatus, setDisplayStatus] = useState<Notebook["status"]>("UNKNOWN");

    const fetchStatus = useCallback(async () => {
        const { data, error } = await get_notebook(experimentId);
        if (error) {
            showError(error);
            return;
        }
        setNotebook(data || UNKNOWN_NOTEBOOK);
    }, [experimentId, showError]);

    const probeNotebook = useCallback(async (path: string): Promise<boolean> => {
        try {
            const response = await fetch(path);
            return response.ok;
        } catch {
            return false;
        }
    }, []);

    useEffect(() => {
        if (notebook.status === "RUNNING" && notebook.path && displayStatus !== "RUNNING") {
            const checkReadiness = async () => {
                const isReady = await probeNotebook(notebook.path);
                setDisplayStatus(isReady ? "RUNNING" : "INITIALIZING");
            };

            setDisplayStatus("INITIALIZING");
            checkReadiness();

            const intervalId = window.setInterval(checkReadiness, 2000);
            return () => window.clearInterval(intervalId);
        } else {
            setDisplayStatus(notebook.status);
        }
    }, [notebook.status, notebook.path, displayStatus, probeNotebook]);

    const spawnNotebook = useCallback(async () => {
        const { error, data } = await spawn_notebook(experimentId);
        if (error) {
            showError(error);
            return;
        }
        setNotebook(data || UNKNOWN_NOTEBOOK);
    }, [experimentId, showError]);

    const stopNotebook = useCallback(async () => {
        const { error } = await delete_notebook(experimentId);
        if (error) {
            showError(error);
            return;
        }
        await fetchStatus();
    }, [experimentId, showError, fetchStatus]);

    const respawnNotebook = useCallback(async () => {
        await stopNotebook();
        await spawnNotebook();
    }, [stopNotebook, spawnNotebook]);

    useEffect(() => {
        setLoading(true);
        fetchStatus().finally(() => setLoading(false));
    }, [fetchStatus]);

    useEffect(() => {
        const isPolling =
            displayStatus === "PENDING" || displayStatus === "INITIALIZING" || displayStatus === "TERMINATING";
        if (!isPolling) return;

        const intervalId = window.setInterval(fetchStatus, 1000);
        return () => window.clearInterval(intervalId);
    }, [displayStatus, fetchStatus]);

    const statusConfig = useMemo(() => STATUS_CONFIG[displayStatus] || STATUS_CONFIG.UNKNOWN, [displayStatus]);
    const StatusIcon = statusConfig.icon;
    const isTransitioning =
        displayStatus === "PENDING" || displayStatus === "INITIALIZING" || displayStatus === "TERMINATING";

    return (
        <Paper
            variant="outlined"
            sx={{
                width: 400,
                height: 200,
                padding: 4,
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
            }}
        >
            {loading ? (
                <CircularProgress />
            ) : (
                <Stack spacing={2}>
                    <Stack direction="row" spacing={1} alignItems="center">
                        {isTransitioning ? (
                            <CircularProgress size={20} />
                        ) : StatusIcon ? (
                            <StatusIcon color={statusConfig.color} />
                        ) : null}
                        <Typography variant="h4">Notebook Status:</Typography>
                        <Chip size="small" label={displayStatus} color={getPodStatusColor(displayStatus)} />
                    </Stack>

                    <Typography variant="body2">{statusConfig.message}</Typography>

                    <Stack direction="row" spacing={2} justifyContent="center">
                        {(displayStatus === "DOWN" || displayStatus === "TERMINATED") && (
                            <Button
                                variant="contained"
                                color="primary"
                                onClick={spawnNotebook}
                                startIcon={<PlayArrow />}
                            >
                                Start
                            </Button>
                        )}
                        {displayStatus === "RUNNING" && (
                            <Button
                                variant="contained"
                                color="primary"
                                href={notebook.path}
                                target="_blank"
                                rel="noopener noreferrer"
                                startIcon={<OpenInNew />}
                            >
                                Open
                            </Button>
                        )}
                        {(displayStatus === "RUNNING" ||
                            displayStatus === "PENDING" ||
                            displayStatus === "INITIALIZING") && (
                            <Button variant="outlined" color="error" onClick={stopNotebook} startIcon={<Stop />}>
                                Stop
                            </Button>
                        )}
                        {(displayStatus === "ERROR" || displayStatus === "UNKNOWN") && (
                            <Button
                                variant="contained"
                                color="warning"
                                onClick={respawnNotebook}
                                startIcon={<Refresh />}
                            >
                                Respawn
                            </Button>
                        )}
                    </Stack>
                </Stack>
            )}
        </Paper>
    );
};

export default NotebookController;

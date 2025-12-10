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

    const fetchStatus = useCallback(async () => {
        const { data, error } = await get_notebook(experimentId);
        if (error) {
            showError(error);
            return;
        }
        setNotebook(data || UNKNOWN_NOTEBOOK);
    }, [experimentId, showError]);

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
        const isPolling = notebook.status === "PENDING" || notebook.status === "TERMINATING";
        if (!isPolling) return;

        const intervalId = window.setInterval(fetchStatus, 1000);
        return () => window.clearInterval(intervalId);
    }, [notebook.status, fetchStatus]);

    const statusConfig = useMemo(() => STATUS_CONFIG[notebook.status] || STATUS_CONFIG.UNKNOWN, [notebook.status]);
    const StatusIcon = statusConfig.icon;
    const isTransitioning = notebook.status === "PENDING" || notebook.status === "TERMINATING";

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
                        <Chip size="small" label={notebook.status} color={getPodStatusColor(notebook.status)} />
                    </Stack>

                    <Typography variant="body2">{statusConfig.message}</Typography>

                    <Stack direction="row" spacing={2} justifyContent="center">
                        {(notebook.status === "DOWN" || notebook.status === "TERMINATED") && (
                            <Button
                                variant="contained"
                                color="primary"
                                onClick={spawnNotebook}
                                startIcon={<PlayArrow />}
                            >
                                Start
                            </Button>
                        )}
                        {notebook.status === "RUNNING" && (
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
                        {(notebook.status === "RUNNING" || notebook.status === "PENDING") && (
                            <Button variant="outlined" color="error" onClick={stopNotebook} startIcon={<Stop />}>
                                Stop
                            </Button>
                        )}
                        {(notebook.status === "ERROR" || notebook.status === "UNKNOWN") && (
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

import { useEffect, useState, useMemo, useCallback } from "react";

import { Power, Rocket, HelpCircle, AlertCircle, Play, Square, RefreshCw, ExternalLink, Loader2 } from "lucide-react";

import { useNotebook, useSpawnNotebook, useStopNotebook } from "@/hooks/use-notebook";
import { Notebook, getPodStatusVariant, statusBadgeClass } from "@/util/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const UNKNOWN_NOTEBOOK: Notebook = {
    id: -1,
    experiment_id: "",
    token: "",
    status: "UNKNOWN",
    path: "",
};

const STATUS_CONFIG = {
    DOWN: {
        Icon: Power,
        message: "Your notebook is not running. Click the button below to start it.",
    },
    TERMINATED: {
        Icon: Power,
        message: "Your notebook is not running. Click the button below to start it.",
    },
    PENDING: {
        Icon: null,
        message: "Your notebook is starting up. This may take a minute.",
    },
    INITIALIZING: {
        Icon: null,
        message: "Your notebook is setting up the environment. This may take a few minutes if using Binder repository.",
    },
    TERMINATING: {
        Icon: null,
        message: "Your notebook is shutting down. Please wait.",
    },
    RUNNING: {
        Icon: Rocket,
        message: "Your notebook is up. Click the button below to open it.",
    },
    ERROR: {
        Icon: AlertCircle,
        message: "There was an error with your notebook. Try respawning it.",
    },
    UNKNOWN: {
        Icon: HelpCircle,
        message: "Notebook status is unknown.",
    },
} as const;

interface NotebookControllerProps {
    experimentId: string;
}

const NotebookController = ({ experimentId }: NotebookControllerProps) => {
    const isTransitioning_status = (s: Notebook["status"]) =>
        s === "PENDING" || s === "INITIALIZING" || s === "TERMINATING";

    // Poll when transitioning
    const [displayStatus, setDisplayStatus] = useState<Notebook["status"]>("UNKNOWN");
    const shouldPoll = isTransitioning_status(displayStatus);

    const { data: notebook = UNKNOWN_NOTEBOOK, isLoading } = useNotebook(experimentId, shouldPoll ? 1000 : false);
    const spawnNotebook = useSpawnNotebook(experimentId);
    const stopNotebook = useStopNotebook(experimentId);

    const probeNotebook = useCallback(async (path: string): Promise<boolean> => {
        try {
            const response = await fetch(path);
            return response.ok;
        } catch {
            return false;
        }
    }, []);

    // Readiness probe when API says RUNNING
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

    const respawnNotebook = async () => {
        await stopNotebook.mutateAsync();
        await spawnNotebook.mutateAsync();
    };

    const statusConfig = useMemo(() => STATUS_CONFIG[displayStatus] || STATUS_CONFIG.UNKNOWN, [displayStatus]);
    const { Icon: StatusIcon, message } = statusConfig;
    const isTransitioning = isTransitioning_status(displayStatus);
    const variant = getPodStatusVariant(displayStatus);

    return (
        <div className="w-96 min-h-48 rounded-md border flex items-center justify-center p-6">
            {isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            ) : (
                <div className="flex flex-col gap-4">
                    <div className="flex items-center gap-2">
                        {isTransitioning ? (
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        ) : StatusIcon ? (
                            <StatusIcon className="h-5 w-5 text-muted-foreground" />
                        ) : null}
                        <span className="font-medium text-sm">Notebook Status:</span>
                        <Badge variant="outline" className={cn("text-xs", statusBadgeClass(variant))}>
                            {displayStatus}
                        </Badge>
                    </div>

                    <p className="text-sm text-muted-foreground">{message}</p>

                    <div className="flex gap-2 justify-center flex-wrap">
                        {(displayStatus === "DOWN" || displayStatus === "TERMINATED") && (
                            <Button
                                variant="default"
                                onClick={() => spawnNotebook.mutate()}
                                disabled={spawnNotebook.isPending}
                            >
                                <Play className="h-4 w-4 mr-1" />
                                Start
                            </Button>
                        )}
                        {displayStatus === "RUNNING" && (
                            <Button variant="default" asChild>
                                <a href={notebook.path} target="_blank" rel="noopener noreferrer">
                                    <ExternalLink className="h-4 w-4 mr-1" />
                                    Open
                                </a>
                            </Button>
                        )}
                        {(displayStatus === "RUNNING" ||
                            displayStatus === "PENDING" ||
                            displayStatus === "INITIALIZING") && (
                            <Button
                                variant="outline"
                                className="text-destructive border-destructive hover:bg-destructive hover:text-destructive-foreground"
                                onClick={() => stopNotebook.mutate()}
                                disabled={stopNotebook.isPending}
                            >
                                <Square className="h-4 w-4 mr-1" />
                                Stop
                            </Button>
                        )}
                        {(displayStatus === "ERROR" || displayStatus === "UNKNOWN") && (
                            <Button
                                variant="default"
                                className="bg-yellow-500 hover:bg-yellow-600 text-white"
                                onClick={respawnNotebook}
                            >
                                <RefreshCw className="h-4 w-4 mr-1" />
                                Respawn
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default NotebookController;

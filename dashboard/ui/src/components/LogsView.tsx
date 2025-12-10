import { useState, useEffect, useCallback } from "react";

import { Paper, Box } from "@mui/material";

export interface LogsViewProps {
    getLogs: () => Promise<string>;
    refreshInterval?: number;
    sx?: object;
}

export default function LogsView(props: LogsViewProps) {
    const { getLogs, refreshInterval, sx } = props;

    const [logs, setLogs] = useState<string>("");

    const fetchLogs = useCallback(async () => {
        const logText = await getLogs();
        setLogs("...\n" + logText);
    }, [getLogs]);

    useEffect(() => {
        fetchLogs();
        if (refreshInterval) {
            const interval = setInterval(fetchLogs, refreshInterval);
            return () => clearInterval(interval);
        }
    }, [fetchLogs, refreshInterval]);

    return (
        <Paper variant="outlined" sx={{ height: 400, width: "100%", p: 2, ...sx }}>
            <Box
                ref={(el: HTMLElement) => el?.scrollTo(0, el.scrollHeight)}
                sx={{ height: "100%", fontFamily: "monospace", overflow: "auto", whiteSpace: "pre-wrap" }}
            >
                {logs || "Loading..."}
            </Box>
        </Paper>
    );
}

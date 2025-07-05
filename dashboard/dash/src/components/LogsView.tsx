import { useState, useEffect } from "react";
import { Paper, Box } from "@mui/material";

export interface LogsViewProps {
    getLogs: () => Promise<string>;
    refreshInterval?: number;
}

export default function LogsView(props: LogsViewProps) {
    const { getLogs, refreshInterval } = props;

    const [logs, setLogs] = useState<string>("");

    const fetchLogs = async () => {
        const logText = await getLogs();
        setLogs("...\n" + logText);
    };

    useEffect(() => {
        fetchLogs();
        if (refreshInterval) {
            const interval = setInterval(fetchLogs, refreshInterval);
            return () => clearInterval(interval);
        }
    }, [getLogs, refreshInterval]);

    return (
        <Paper variant="outlined" sx={{ height: 400, width: "100%", p: 2, boxSizing: "border-box" }}>
            <Box
                ref={(el: HTMLElement) => el?.scrollTo(0, el.scrollHeight)}
                sx={{
                    height: "100%",
                    fontFamily: "monospace",
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                }}
            >
                {logs || "Loading logs..."}
            </Box>
        </Paper>
    );
}

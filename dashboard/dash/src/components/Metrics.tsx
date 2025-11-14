import { useEffect, useState } from "react";

import { Typography, Card, Grid2 as Grid, CardContent, Stack, LinearProgress, Box } from "@mui/material";
import { Memory, DeveloperBoard, Storage } from "@mui/icons-material";

import { get_metrics } from "@/util/api";
import { ResourceUsage } from "@/util/types";

const formatBytes = (bytes: number): string => {
    const gb = bytes / (1024 ** 3);
    return gb.toFixed(2);
};

const formatMillicores = (millicores: number): string => {
    const cores = millicores / 1000;
    return cores.toFixed(2);
};

const Metrics = () => {
    const [metrics, setMetrics] = useState<ResourceUsage | null>(null);

    const fetchMetrics = async () => {
        const { data, error } = await get_metrics();
        if (error) {
            console.error(error);
            return;
        }
        setMetrics(data);
    };

    useEffect(() => {
        fetchMetrics();
    }, []);

    if (!metrics) {
        return null;
    }

    const cpuUsagePercent = metrics.limits.cpu > 0 
        ? (metrics.requests.cpu / metrics.limits.cpu) * 100 
        : 0;
    const memoryUsagePercent = metrics.limits.memory > 0 
        ? (metrics.requests.memory / metrics.limits.memory) * 100 
        : 0;
    const storageUsagePercent = metrics.limits.storage > 0 
        ? (metrics.requests.storage / metrics.limits.storage) * 100 
        : 0;

    return (
        <Grid container spacing={2} p={4}>
            <Grid size={4}>
                <Card>
                    <CardContent>
                        <Stack direction="row" alignItems="center" spacing={2} mb={2}>
                            <Stack direction="column" flex={1}>
                                <Typography variant="subtitle1">CPU</Typography>
                                <Typography variant="h4">
                                    {formatMillicores(metrics.requests.cpu)} / {formatMillicores(metrics.limits.cpu)} cores
                                </Typography>
                            </Stack>
                            <DeveloperBoard color="info" fontSize="large" />
                        </Stack>
                        <Box>
                            <LinearProgress 
                                variant="determinate" 
                                value={Math.min(cpuUsagePercent, 100)} 
                                color={cpuUsagePercent > 80 ? "warning" : "info"}
                            />
                            <Typography variant="caption" color="text.secondary" mt={0.5}>
                                {cpuUsagePercent.toFixed(1)}% allocated
                            </Typography>
                        </Box>
                    </CardContent>
                </Card>
            </Grid>
            <Grid size={4}>
                <Card>
                    <CardContent>
                        <Stack direction="row" alignItems="center" spacing={2} mb={2}>
                            <Stack direction="column" flex={1}>
                                <Typography variant="subtitle1">Memory</Typography>
                                <Typography variant="h4">
                                    {formatBytes(metrics.requests.memory)} / {formatBytes(metrics.limits.memory)} GB
                                </Typography>
                            </Stack>
                            <Memory color="warning" fontSize="large" />
                        </Stack>
                        <Box>
                            <LinearProgress 
                                variant="determinate" 
                                value={Math.min(memoryUsagePercent, 100)} 
                                color={memoryUsagePercent > 80 ? "error" : "warning"}
                            />
                            <Typography variant="caption" color="text.secondary" mt={0.5}>
                                {memoryUsagePercent.toFixed(1)}% allocated
                            </Typography>
                        </Box>
                    </CardContent>
                </Card>
            </Grid>
            <Grid size={4}>
                <Card>
                    <CardContent>
                        <Stack direction="row" alignItems="center" spacing={2} mb={2}>
                            <Stack direction="column" flex={1}>
                                <Typography variant="subtitle1">Storage</Typography>
                                <Typography variant="h4">
                                    {formatBytes(metrics.requests.storage)} / {formatBytes(metrics.limits.storage)} GB
                                </Typography>
                            </Stack>
                            <Storage color="success" fontSize="large" />
                        </Stack>
                        <Box>
                            <LinearProgress 
                                variant="determinate" 
                                value={Math.min(storageUsagePercent, 100)} 
                                color={storageUsagePercent > 80 ? "error" : "success"}
                            />
                            <Typography variant="caption" color="text.secondary" mt={0.5}>
                                {storageUsagePercent.toFixed(1)}% used
                            </Typography>
                        </Box>
                    </CardContent>
                </Card>
            </Grid>
        </Grid>
    );
};

export default Metrics;

import { useEffect, useState } from "react";

import { Typography, Card, Grid2 as Grid, CardContent, Stack } from "@mui/material";
import { Memory, DeveloperBoard, RocketLaunch } from "@mui/icons-material";

import { get_metrics } from "@/util/api";
import { ResourceUsage } from "@/util/types";

const Metrics = () => {
    const [metrics, setMetrics] = useState<ResourceUsage>({ cpu: 0, gpu: 0, memory: 0 });

    const fetchMetrics = async () => {
        const { data, error } = await get_metrics();
        if (error) {
            console.error(error);
            return;
        }
        setMetrics(data || { cpu: 0, gpu: 0, memory: 0 });
    };

    useEffect(() => {
        fetchMetrics();
    }, []);

    return (
        <Grid container spacing={2} p={4}>
            <Grid size={3}>
                <Card>
                    <CardContent>
                        <Stack direction="row" alignItems="center" spacing={2}>
                            <DeveloperBoard color="info" fontSize="large" />
                            <Stack direction="column">
                                <Typography variant="body1">CPU</Typography>
                                <Typography variant="h3">{metrics.cpu} cores</Typography>
                            </Stack>
                        </Stack>
                    </CardContent>
                </Card>
            </Grid>
            <Grid size={3}>
                <Card>
                    <CardContent>
                        <Stack direction="row" alignItems="center" spacing={2}>
                            <RocketLaunch color="success" fontSize="large" />
                            <Stack direction="column">
                                <Typography variant="body1">GPU</Typography>
                                <Typography variant="h3">{metrics.gpu} cores</Typography>
                            </Stack>
                        </Stack>
                    </CardContent>
                </Card>
            </Grid>
            <Grid size={3}>
                <Card>
                    <CardContent>
                        <Stack direction="row" alignItems="center" spacing={2}>
                            <Memory color="warning" fontSize="large" />
                            <Stack direction="column">
                                <Typography variant="body1">Memory</Typography>
                                <Typography variant="h3">{metrics.memory} GB</Typography>
                            </Stack>
                        </Stack>
                    </CardContent>
                </Card>
            </Grid>
        </Grid>
    );
};

export default Metrics;

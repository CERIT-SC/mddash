import { useState, useEffect } from "react";
import { Typography, Card, Grid2 as Grid, CardContent } from "@mui/material";

import Experiments from "../components/Experiments";
import { USER } from "../util/const";
import { get_metrics } from "../util/api";

interface Metrics {
    cpu: number;
    gpu: number;
    memory: number;
}

const Home = () => {
    const [metrics, setMetrics] = useState<Metrics>({ cpu: 0, gpu: 0, memory: 0 });

    const fetchMetrics = async () => {
        const { data, error } = await get_metrics();
        if (error) {
            console.error(error);
            return;
        }
        setMetrics(data.data);
    };

    useEffect(() => {
        fetchMetrics();
    }, []);

    return (
        <>
            <Typography variant="h2">Welcome to your dashboard, {USER}!</Typography>

            <Typography variant="h3">My Experiments</Typography>

            <Experiments />

            <Typography variant="h3">Service Utilization</Typography>

            <Grid container spacing={2} p={4}>
                <Grid size={3}>
                    <Card>
                        <CardContent>
                            <Typography variant="h4">CPU</Typography>
                            <Typography variant="h6">{metrics.cpu} cores</Typography>
                        </CardContent>
                    </Card>
                </Grid>
                <Grid size={3}>
                    <Card>
                        <CardContent>
                            <Typography variant="h4">GPU</Typography>
                            <Typography variant="h6">{metrics.gpu} cores</Typography>
                        </CardContent>
                    </Card>
                </Grid>
                <Grid size={3}>
                    <Card>
                        <CardContent>
                            <Typography variant="h4">Memory</Typography>
                            <Typography variant="h6">{metrics.memory} GB</Typography>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>

            <Typography variant="h3">Documentation</Typography>

            <Typography variant="body1">There is no documentation yet :P</Typography>
        </>
    );
};

export default Home;

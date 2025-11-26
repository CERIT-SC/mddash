import { Typography } from "@mui/material";

import Experiments from "@/components/Experiments";
import Metrics from "@/components/Metrics";

const Home = () => {
    return (
        <>
            <Typography variant="h1">My Experiments</Typography>

            <Experiments />

            <Typography variant="h1">Resource Usage</Typography>

            <Metrics />

            <Typography variant="h1">Documentation</Typography>

            <Typography variant="body1" p={4}>
                There is no documentation yet :P
            </Typography>
        </>
    );
};

export default Home;

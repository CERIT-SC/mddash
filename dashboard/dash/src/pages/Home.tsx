import { Typography, Card, Grid2 as Grid, CardContent } from '@mui/material'

import Experiments from '../components/Experiments'
import { USER } from '../util/const'

const Home = () => {
    return (
        <>
            <Typography variant="h2">
                Welcome to your dashboard, {USER}!
            </Typography>

            <Typography variant="h3">
                My Experiments
            </Typography>

            <Experiments />

            <Typography variant="h3">
                Service Utilization
            </Typography>

            {/* NOTE: Service utilization will be fetched from api */}
            {/* TODO: Display the different services in a loop */}

            <Grid container spacing={2} p={4}>
                <Grid size={3}>
                    <Card>
                        <CardContent>
                            <Typography variant="h4">CPU</Typography>
                            <Typography variant="h6">🔥%</Typography>
                        </CardContent>
                    </Card>
                </Grid>
                <Grid size={3}>
                <Card>
                        <CardContent>
                            <Typography variant="h4">GPU</Typography>
                            <Typography variant="h6">🔥%</Typography>
                        </CardContent>
                    </Card>
                </Grid>
                <Grid size={3}>
                <Card>
                        <CardContent>
                            <Typography variant="h4">Memory</Typography>
                            <Typography variant="h6">🔥%</Typography>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>

            <Typography variant="h3">
                Documentation
            </Typography>

            <Typography variant="body1">
                There is no documentation yet :P
            </Typography>
        </>
    )
}

export default Home

import { useState, useEffect } from 'react'
import { Typography, Card, CardActionArea, CardActions, Grid2 as Grid, Stack, CardContent, Button } from '@mui/material'
import { Add } from '@mui/icons-material'
import { BASE_PATH } from '../util/const'

import { Experiment } from '../util/types'
import { delete_experiment, get_experiments } from '../util/api'
import ErrorMessage from './ErrorMessage'

const Experiments = () => {
    const [experiments, setExperiments] = useState<Experiment[]>([])
    const [errorMessage, setErrorMessage] = useState<string>('')

    const getExperiments = async () => {
        let data: any = []

        try {
            data = await get_experiments()

            console.log(data)

            if (data.status === 'error')
                setErrorMessage(data.message)
            else
                setErrorMessage('')
        }
        catch (error) {
            setErrorMessage('Failed to fetch experiments.')
            console.error(error)
        }

        setExperiments(data.data || [])
    }

    const deleteExperiment = async (id: string) => {
        const data = await delete_experiment(id);

        if (data.status === 'success')
            getExperiments()
        else
            setErrorMessage(data.message)
    }

    useEffect(() => {
        getExperiments();
    }, []);

    return (
        <Stack spacing={2} p={4}>

            <Grid container spacing={2} p={4} >

                {experiments.map(experiment => (
                    <Grid size={3} key={experiment.id} sx={{ display: 'flex' }}>
                        <Card sx={{ padding: 2, flexGrow: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                            <CardContent>
                                <Typography variant="h4">{experiment.name}</Typography>
                                <Typography variant="body1">Status: {experiment.status}</Typography>
                                <Typography variant="body1">Step: {experiment.step}</Typography>
                            </CardContent>
                            <CardActions sx={{ alignSelf: 'flex-end', width: '100%', justifyContent: 'center' }}>
                                <Button size="small" variant='contained' href={`${BASE_PATH}/${experiment.id}/wizard`}>Wizard</Button>
                                <Button size="small" variant='outlined' color="error" onClick={() => {deleteExperiment(experiment.id)}}>Delete</Button>
                            </CardActions>
                        </Card>
                    </Grid>
                ))}

                <Grid size={3} sx={{ display: 'flex' }}>
                    <Card sx={{ flexGrow: 1 }}>
                        <CardActionArea href={`${BASE_PATH}/new`}>
                            <Stack alignItems="center" justifyContent="center" spacing={2} p={4}>
                                <Add sx={{ width: 75, height: 75 }} />
                                <Typography variant="h4" textAlign="center">New Experiment</Typography>
                            </Stack>
                        </CardActionArea>
                    </Card>
                </Grid>
            </Grid>

            {errorMessage && <ErrorMessage message={errorMessage} />}
        </Stack>
    )
}

export default Experiments

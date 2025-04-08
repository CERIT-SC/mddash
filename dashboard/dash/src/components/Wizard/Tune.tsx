import { useEffect, useState } from 'react';
import { Box, Stack, Button, Typography, CircularProgress } from '@mui/material'

import { WizardStepperProps } from "./Stepper"
import { tuner_status, run_tuner, kill_tuner } from '../../util/api';

const WizardTune = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;
    const [ loading, setLoading ] = useState(false);
    const [ tunerUp, setTunerUp ] = useState(false);
    const [ tunerStatus, setTunerStatus ] = useState({});


    console.log(experiment);
    console.log(setErrorMessage);

    const getTuner = async () => {
        setLoading(true);
        const { data, error } = await tuner_status(experiment.id);
        setErrorMessage(error || '');
        setTunerUp(data?.message === 'up');
        setTunerStatus(data?.status || {});
        setLoading(false);
    }

    const runTuner = async () => {
        const { error } = await run_tuner(experiment.id);
        setErrorMessage(error || '');
        getTuner();
    }

    const killTuner = async () => {
        const { error } = await kill_tuner(experiment.id);
        setErrorMessage(error || '');
        getTuner();
    }

    useEffect(() => {
        getTuner();
    }, []);

    return (
        <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>

            { loading && (
                <CircularProgress />
            ) || (
                <Stack spacing={2} direction="column">
                    {tunerUp && (
                        <>
                            <Typography variant="h5">Tuner running 🚀</Typography>
                            <Button variant="contained" color="error" onClick={killTuner}>Kill tuner 🔪</Button>
                            <h3>TODO: create a nice overview for this data:</h3>
                            <pre>{ JSON.stringify(tunerStatus, null, 4) }</pre>
                        </>
                    ) || (
                        <>
                            <Typography variant="h5">Tuner isn't running 💔</Typography>
                            <Button variant="contained" color="primary" onClick={runTuner}>Run tuner</Button>
                        </>
                    )}
                </Stack>
            )}
        </Box>
    );
}

export default WizardTune;

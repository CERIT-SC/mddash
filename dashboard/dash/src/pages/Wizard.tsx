import { useParams } from 'react-router-dom';
import { Paper, Typography } from '@mui/material';
import { useEffect, useState } from 'react';

import WizardStepper from '../components/Wizard/Stepper'
import { Experiment } from '../util/types';
import { get_experiment } from '../util/api';
import ErrorMessage from '../components/ErrorMessage';

const Wizard = () => {
    const { id } = useParams<{ id: string }>();

    const [experiment, setExperiment] = useState<Experiment | null>(null);
    const [errorMessage, setErrorMessage] = useState<string>('');

    const getExperiment = async () => {
        if (!id) return;

        const data = await get_experiment(id);

        if (data.status === 'error')
            setErrorMessage(data.message || 'Failed to fetch experiment');

        setExperiment(data.data || null);
    }

    useEffect(() => {
        getExperiment();
    }, []);

    return (
        <div>

            <Typography variant="h2">
                Wizard
            </Typography>

            {errorMessage && <ErrorMessage message={errorMessage} />}

            {experiment && (
                <Paper elevation={2} sx={{ p: 4, mt: 4 }}>
                    <WizardStepper experiment={experiment} setExperiment={setExperiment} />
                </Paper>
            )}
        </div>
    )
}

export default Wizard

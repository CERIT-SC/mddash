import { useEffect, useState } from 'react';
import { Box, Button, Typography } from '@mui/material'

import { WizardStepperProps } from "./Stepper"
import { get_notebook, spawn_notebook, delete_notebook, ApiError } from '../../util/api';


const WizardSetup = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;
    const [ notebookUp, setNotebookUp ] = useState(false);
    const [ notebookPath, setNotebookPath ] = useState('');

    const getNotebook = async () => {
        let data;

        try {
            data = await get_notebook(experiment.id);
            setNotebookUp(data.message === 'up');
            setNotebookPath(data.path);
        }
        catch (error) {
            if (error instanceof ApiError)
                setErrorMessage(error.message);
            else
                setErrorMessage('Failed to get notebook status.');
        }
    }

    const spawnNotebook = async () => {
        try {
            await spawn_notebook(experiment.id);
            getNotebook();
        }
        catch (error) {
            if (error instanceof ApiError)
                setErrorMessage(error.message);
            else
                setErrorMessage('Failed to spawn notebook.');
        }
    }

    const deleteNotebook = async () => {
        try {
            await delete_notebook(experiment.id);
            getNotebook();
        }
        catch (error) {
            if (error instanceof ApiError)
                setErrorMessage(error.message);
            else
                setErrorMessage('Failed to delete notebook.');
        }
    }

    useEffect(() => {
        getNotebook();
    }, []);

    return (
        <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Typography variant="h5">Notebook status: {notebookUp ? 'up' : 'down'}</Typography>
            <Button variant="contained" color="primary" onClick={spawnNotebook}>Spawn Jupyter Notebook</Button>
            <Button variant="contained" color="success" disabled={!notebookUp} href={notebookPath}>Open Jupyter Notebook</Button>
            <Button variant="contained" color="error" onClick={deleteNotebook}>Delete Jupyter Notebook</Button>
        </Box>
    )
}

export default WizardSetup

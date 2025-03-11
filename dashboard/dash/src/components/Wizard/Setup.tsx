import { useEffect, useState } from 'react';
import { Box, Button, Typography } from '@mui/material'

import { WizardStepperProps } from "./Stepper"
import { get_notebook, spawn_notebook, delete_notebook } from '../../util/api';


const WizardSetup = (props: WizardStepperProps) => {
    const { experiment, setErrorMessage } = props;
    const [ notebookUp, setNotebookUp ] = useState(false);
    const [ notebookPath, setNotebookPath ] = useState('');

    const getNotebook = async () => {
        const { data, error } = await get_notebook(experiment.id);
        setErrorMessage(error || '');
        setNotebookUp(data?.status === 'up');
        setNotebookPath(data?.path || '');
    }

    const spawnNotebook = async () => {
        const { error } = await spawn_notebook(experiment.id);
        setErrorMessage(error || '');
    }

    const deleteNotebook = async () => {
        const { error } = await delete_notebook(experiment.id);
        setErrorMessage(error || '');
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

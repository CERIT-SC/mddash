import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Stack, Button, TextField, Typography, FormControl, Radio, RadioGroup, FormLabel, FormControlLabel } from '@mui/material';

import Dropzone from '../components/Dropzone';
import ErrorMessage from '../components/ErrorMessage';
import { BASE_PATH } from '../util/const';
import { create_experiment } from '../util/api';

const New = () => {
    const navigate = useNavigate();

    const [nameError, setNameError] = useState(false);
    const [typeError, setTypeError] = useState(false);
    const [typeAuxError, setTypeAuxError] = useState(false);

    const [type, setType] = useState('');
    const [errorMessage, setErrorMessage] = useState('');

    const validateForm = (event: React.FormEvent<HTMLFormElement>) => {
        setErrorMessage('');
        event.preventDefault();

        const form = event.currentTarget;
        const name = form['experiment-name'].value;
        const type = form['type'].value;

        const pdbId = form['pdb-id']?.value;
        const repoUrl = form['repo-url']?.value;
        const file = form['simulation-file']?.files[0];
        
        let typeAuxError = false;

        if ((type === 'pdb' && !pdbId) || (type === 'repo' && !repoUrl) || (type === 'file' && !file))
            typeAuxError = true;

        setNameError(!name);
        setTypeError(!type);
        setTypeAuxError(typeAuxError);

        if (name && type && !typeAuxError)
            return true;

        setErrorMessage('Please fill in all required fields');
        return false;
    }

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = event.currentTarget;

        if (!validateForm(event))
            return;

        const formData = new FormData(form);

        try {
            const data = await create_experiment(formData);
            console.log('Experiment created:', data);
            navigate(`${BASE_PATH}/${data.data.id}/wizard`);
        }
        catch (error: Error | any) {
            setErrorMessage(error.message);
            console.error(error);
        }
    };

    const handleTypeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setType(event.target.value);
    }


    return (
        <>
            <Typography variant="h2" gutterBottom>
                New Experiment
            </Typography>

            <Stack
                component="form"
                autoComplete="off"
                onSubmit={handleSubmit} 
                onChange={(e) => {if (nameError || typeError || typeAuxError) validateForm(e)}}
                spacing={4}
                p={4}
            >
                <TextField name="experiment-name" label="Experiment Name" variant="outlined" error={nameError} />

                <FormControl error={typeError}>
                    <FormLabel>Initial Data</FormLabel>
                    <RadioGroup name="type" onChange={handleTypeChange}>
                        <FormControlLabel value="pdb" control={<Radio />} label="PDB ID" />
                        <FormControlLabel value="repo" control={<Radio />} label="Repository URL" />
                        <FormControlLabel value="file" control={<Radio />} label="TPR/XTC file" />
                    </RadioGroup>
                </FormControl>

                {type === 'pdb' && (
                    <TextField id="pdb-id" label="PDB ID" variant="outlined" error={typeAuxError} />
                ) ||
                type === 'repo' && (
                    <TextField id="repo-url" label="Repository URL" variant="outlined" error={typeAuxError} />
                ) ||
                type === 'file' && (
                    <Dropzone
                        inputName="simulation-file"
                        accept={{'application/octet-stream': ['.tpr', '.xtc']}}
                        maxFiles={1}
                    />
                )}

                <Button variant="contained" type="submit">
                    Create Experiment
                </Button>

                {errorMessage && <ErrorMessage message={errorMessage} />}
            </Stack>
        </>
    );
};

export default New;

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Stack, Button, TextField, Typography, FormControl, Radio, RadioGroup, FormLabel, FormControlLabel } from '@mui/material';

import Dropzone from '../components/Dropzone';
import ErrorMessage from '../components/ErrorMessage';
import { BASE_PATH } from '../util/const';
import { create_experiment } from '../util/api';

const New = () => {
    const navigate = useNavigate();

    const [name, setName] = useState('');
    const [type, setType] = useState('');
    const [pdbId, setPdbId] = useState('');
    const [repoUrl, setRepoUrl] = useState('');
    const [file, setFile] = useState<File | null>(null);

    const [nameError, setNameError] = useState(false);
    const [typeError, setTypeError] = useState(false);
    const [typeAuxError, setTypeAuxError] = useState(false);
    const [errorMessage, setErrorMessage] = useState('');

    const validateForm = () => {
        setErrorMessage('');

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

        if (!validateForm())
            return;

        const formData = new FormData();
        formData.append('experiment-name', name);
        formData.append('type', type);
        if (type === 'pdb') formData.append('pdb-id', pdbId);
        if (type === 'repo') formData.append('repo-url', repoUrl);
        if (type === 'file' && file) formData.append('simulation-file', file);

        const { data, error } = await create_experiment(formData);
        setErrorMessage(error || '');

        console.log('Experiment created:', data);

        if (!error)
            navigate(`${BASE_PATH}/${data.data.id}/wizard`);
    };

    const handleTypeChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setType(event.target.value);
        setPdbId('');
        setRepoUrl('');
        setFile(null);
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
                spacing={4}
                p={4}
            >
                <TextField
                    name="experiment-name"
                    label="Experiment Name"
                    variant="outlined"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    error={nameError}
                />

                <FormControl error={typeError}>
                    <FormLabel>Initial Data</FormLabel>
                    <RadioGroup name="type" value={type} onChange={handleTypeChange}>
                        <FormControlLabel value="pdb" control={<Radio />} label="PDB ID" />
                        <FormControlLabel value="repo" control={<Radio />} label="Repository URL" />
                        <FormControlLabel value="file" control={<Radio />} label="TPR/XTC file" />
                    </RadioGroup>
                </FormControl>

                {type === 'pdb' && (
                    <TextField
                        id="pdb-id"
                        label="PDB ID"
                        variant="outlined"
                        value={pdbId}
                        onChange={(e) => setPdbId(e.target.value)}
                        error={typeAuxError}
                    />
                )}
                {type === 'repo' && (
                    <TextField
                        id="repo-url"
                        label="Repository URL"
                        variant="outlined"
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                        error={typeAuxError}
                    />
                )}
                {type === 'file' && (
                    <Dropzone
                        inputName="simulation-file"
                        accept={{'application/octet-stream': ['.tpr', '.xtc']}}
                        maxFiles={1}
                        onDrop={(acceptedFiles) => setFile(acceptedFiles[0])}
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

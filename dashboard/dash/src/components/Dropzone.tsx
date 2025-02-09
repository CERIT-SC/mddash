import { useState } from 'react';
import { useDropzone, DropzoneOptions, FileRejection, DropEvent } from 'react-dropzone';
import { Typography, Paper, alpha, useTheme, Stack, List, ListItem, ListItemAvatar, ListItemText, SxProps } from '@mui/material';
import { Check } from '@mui/icons-material';

import ErrorMessage from './ErrorMessage';

interface DropzoneProps extends DropzoneOptions {
    inputName: string;
    sx?: SxProps;
}


const Dropzone = (props: DropzoneProps) => {
    const { inputName, sx, onDrop, onError, ...dropzoneOptions } = props;

    const [files, setFiles] = useState<File[]>([]);
    const [error, setError] = useState<Error>();

    const theme = useTheme();
    const transparentPrimary = alpha(theme.palette.primary.main, 0.4);

    const handleDrop = (acceptedFiles: File[], fileRejections: FileRejection[], event: DropEvent) => {
        if (fileRejections.length > 0) {
            setError(new Error(fileRejections[0].errors[0].message));
        } else {
            setError(undefined);
        }

        setFiles(acceptedFiles);

        if (onDrop) {
            onDrop(acceptedFiles, fileRejections, event);
        }
    };
    
    const handleError = (err: Error) => {
        setError(err);

        if (onError) {
            onError(err);
        }
    }

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop: handleDrop, onError: handleError, ...dropzoneOptions });

    const formatFileSize = (size: number) => {
        if (size < 1024) {
            return `${size} B`;
        } else if (size < 1024 * 1024) {
            return `${(size / 1024).toFixed(2)} KB`;
        } else if (size < 1024 * 1024 * 1024) {
            return `${(size / 1024 / 1024).toFixed(2)} MB`;
        } else {
            return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`;
        }
    }

    return (
        <Stack spacing={4} sx={sx}>
            <Paper
                {...getRootProps()}
                sx={{
                    p: 2,
                    textAlign: 'center',
                    color: 'text.secondary',
                    border: '2px dashed',
                    borderColor: isDragActive ? 'primary.main' : 'text.secondary',
                    backgroundColor: isDragActive ? transparentPrimary : 'background.paper',
                    cursor: 'pointer',
                }}
            >
                <input name={inputName} {...getInputProps()} />
                {isDragActive ? (
                    <Typography variant="h6">Drop the files here...</Typography>
                ) : (
                    <Typography variant="h6">Drop files here or click.</Typography>
                )}
            </Paper>

            {error && (
                <ErrorMessage message={error.message} />
            )}

            {files.length > 0 && (
                <Paper elevation={2}>
                    <List>
                        {files.map((file, index) => (
                            <ListItem key={index}>
                                <ListItemAvatar>
                                    <Check />
                                </ListItemAvatar>
                                <ListItemText primary={file.name} secondary={formatFileSize(file.size)} />
                            </ListItem>
                        ))}
                    </List>
                </Paper>
            )}
        </Stack>
    );
};

export default Dropzone;

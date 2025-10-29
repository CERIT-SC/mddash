import { useState } from "react";

import { useDropzone, DropzoneOptions, FileRejection, DropEvent, Accept } from "react-dropzone";
import {
    Typography,
    Paper,
    alpha,
    useTheme,
    Stack,
    List,
    ListItem,
    ListItemAvatar,
    ListItemText,
    SxProps,
} from "@mui/material";
import { Check } from "@mui/icons-material";

import { useNotification } from "@/contexts/NotificationContext";
import { formatFileSize } from "@/util/helpers";

const getAcceptedExtensions = (acceptedTypes: Accept) => {
    const extensions: string[] = [];
    for (const key in acceptedTypes) {
        if (acceptedTypes.hasOwnProperty(key)) {
            extensions.push(...acceptedTypes[key]);
        }
    }
    return extensions;
};

interface DropzoneProps extends DropzoneOptions {
    inputName: string;
    sx?: SxProps;
}

const Dropzone = (props: DropzoneProps) => {
    const { inputName, sx, onDrop, onError, ...dropzoneOptions } = props;

    const [files, setFiles] = useState<File[]>([]);
    const { showError } = useNotification();

    const theme = useTheme();
    const transparentPrimary = alpha(theme.palette.primary.main, 0.4);

    const handleDrop = (acceptedFiles: File[], fileRejections: FileRejection[], event: DropEvent) => {
        if (fileRejections.length > 0) {
            showError(fileRejections[0].errors[0].message);
        }

        setFiles(acceptedFiles);
        onDrop?.(acceptedFiles, fileRejections, event);
    };

    const handleError = (err: Error) => {
        showError(err.message);
        onError?.(err);
    };

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop: handleDrop,
        onError: handleError,
        ...dropzoneOptions,
    });

    const acceptedExtensions = getAcceptedExtensions(dropzoneOptions.accept || {})
        .map((ext) => `*${ext}`)
        .join(", ");

    return (
        <Stack spacing={4} sx={sx}>
            <Paper
                {...getRootProps()}
                sx={{
                    p: 2,
                    textAlign: "center",
                    color: "text.secondary",
                    border: "2px dashed",
                    borderColor: isDragActive ? "primary.main" : "text.secondary",
                    backgroundColor: isDragActive ? transparentPrimary : "background.paper",
                    cursor: "pointer",
                }}
            >
                <input name={inputName} {...getInputProps()} />
                {isDragActive ? (
                    <Typography variant="h4">Drop the files here...</Typography>
                ) : (
                    <Typography variant="h4">Drop files here or click.</Typography>
                )}
                {acceptedExtensions && (
                    <Typography variant="body2">Accepted file types: {acceptedExtensions}</Typography>
                )}
            </Paper>

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

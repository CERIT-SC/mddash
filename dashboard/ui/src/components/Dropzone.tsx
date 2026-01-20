import { useState, Fragment } from "react";

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
    Avatar,
    Divider,
    IconButton,
} from "@mui/material";
import { Check, CloudUpload, Delete } from "@mui/icons-material";

import { useNotification } from "@/contexts/useNotification";
import { formatFileSize } from "@/util/helpers";

const getAcceptedExtensions = (acceptedTypes: Accept): string =>
    Object.values(acceptedTypes)
        .flat()
        .map((ext: string) => `*${ext}`)
        .join(", ");

interface DropzoneProps extends DropzoneOptions {
    inputName: string;
    sx?: SxProps;
    onFilesChange?: (files: File[]) => void;
}

const Dropzone = (props: DropzoneProps) => {
    const { inputName, sx, onDrop, onError, onFilesChange, ...dropzoneOptions } = props;

    const [files, setFiles] = useState<File[]>([]);
    const { showError } = useNotification();

    const theme = useTheme();
    const transparentPrimary = alpha(theme.palette.primary.main, 0.4);

    const handleDrop = (acceptedFiles: File[], fileRejections: FileRejection[], event: DropEvent) => {
        if (fileRejections.length > 0) {
            showError(fileRejections[0].errors[0].message);
        }

        const newFiles = [...files, ...acceptedFiles];
        setFiles(newFiles);
        onDrop?.(acceptedFiles, fileRejections, event);
        onFilesChange?.(newFiles);
    };

    const removeFile = (index: number) => {
        const newFiles = [...files];
        newFiles.splice(index, 1);
        setFiles(newFiles);
        onFilesChange?.(newFiles);
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

    const acceptedExtensions = dropzoneOptions.accept ? getAcceptedExtensions(dropzoneOptions.accept) : "";

    return (
        <Stack spacing={2} sx={sx}>
            <Paper
                variant="outlined"
                {...getRootProps()}
                sx={{
                    p: 4,
                    color: "text.secondary",
                    textAlign: "center",
                    border: "2px dashed",
                    borderColor: isDragActive ? "primary.main" : undefined,
                    bgcolor: isDragActive ? transparentPrimary : undefined,
                    cursor: "pointer",
                    transition: "all 0.2s",
                    "&:hover": {
                        borderColor: "primary.main",
                        bgcolor: transparentPrimary,
                    },
                }}
            >
                <input name={inputName} {...getInputProps()} />
                <CloudUpload sx={{ fontSize: 48, color: isDragActive ? "primary.main" : "text.secondary" }} />
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
                <Paper variant="outlined">
                    <List disablePadding>
                        {files.map((file, index) => (
                            <Fragment key={`${file.name}-${index}`}>
                                <ListItem
                                    secondaryAction={
                                        <IconButton
                                            edge="end"
                                            aria-label="delete"
                                            onClick={() => removeFile(index)}
                                            size="small"
                                        >
                                            <Delete fontSize="small" />
                                        </IconButton>
                                    }
                                >
                                    <ListItemAvatar>
                                        <Avatar sx={{ bgcolor: "success.main", width: 32, height: 32 }}>
                                            <Check fontSize="small" />
                                        </Avatar>
                                    </ListItemAvatar>
                                    <ListItemText primary={file.name} secondary={formatFileSize(file.size)} />
                                </ListItem>
                                {index < files.length - 1 && <Divider component="li" />}
                            </Fragment>
                        ))}
                    </List>
                </Paper>
            )}
        </Stack>
    );
};

export default Dropzone;

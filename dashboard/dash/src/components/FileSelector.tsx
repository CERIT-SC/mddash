import React, { useState, useEffect } from 'react';
import { FormControl, InputLabel, Select, MenuItem, SelectChangeEvent } from '@mui/material';

import { find_files } from '../util/api';

export interface FileSelectorProps {
    experimentId: string;
    extension: string;
    onFileSelected: (filePath: string) => void;
    setErrorMessage?: (message: string) => void;
    disabled?: boolean;
    width?: React.CSSProperties['width'];
    height?: React.CSSProperties['height'];
}

interface FileOption {
    name: string;
    url: string;
    size: number;
}

export default function FileSelector(props: FileSelectorProps) {
    const { experimentId, extension, onFileSelected, setErrorMessage, disabled, width } = props;
    const [availableFiles, setAvailableFiles] = useState<FileOption[]>([]);
    const [selectedFile, setSelectedFile] = useState<string>('');
    
    const fetchFiles = async () => {
        const { data, error } = await find_files(experimentId, extension);
        setErrorMessage?.(error || "");
        setAvailableFiles(data.data || []);
    }

    useEffect(() => {
        fetchFiles();
    }, [experimentId, extension]);

    const handleFileChange = (event: SelectChangeEvent) => {
        const selectedUrl = event.target.value;
        setSelectedFile(selectedUrl);
        onFileSelected(selectedUrl);
    };

    return (
        <FormControl disabled={disabled} style={{ width: width || '100%' }}>
            <InputLabel id="file-selector-label">
                Select {extension.toUpperCase()} file
            </InputLabel>
            <Select
                labelId="file-selector-label"
                value={selectedFile}
                label={`Select ${extension.toUpperCase()} file`}
                onChange={handleFileChange}
            >
                {availableFiles.map((file) => (
                    <MenuItem key={file.name} value={file.url}>
                        {file.name} ({(file.size / 1024).toFixed(1)} KB)
                    </MenuItem>
                ))}
            </Select>
        </FormControl>
    );
}

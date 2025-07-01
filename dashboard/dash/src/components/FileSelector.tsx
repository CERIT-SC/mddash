import React, { useState, useEffect } from "react";
import { FormControl, InputLabel, Select, MenuItem, SelectChangeEvent } from "@mui/material";

import { find_files } from "../util/api";
import { FileOption } from "../util/types";


const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
};

export interface FileSelectorProps {
    experimentId: string;
    extension: string;
    onFileSelected: (filePath: string) => void;
    setErrorMessage?: (message: string) => void;
    disabled?: boolean;
    width?: React.CSSProperties["width"];
    height?: React.CSSProperties["height"];
}

const FileSelector = (props: FileSelectorProps) => {
    const { experimentId, extension, onFileSelected, setErrorMessage, disabled, width } = props;
    const [availableFiles, setAvailableFiles] = useState<FileOption[]>([]);
    const [selectedFile, setSelectedFile] = useState<string>("");

    const fetchFiles = async () => {
        const { data, error } = await find_files(experimentId, extension);
        setErrorMessage?.(error || "");
        setAvailableFiles(data || []);
    };

    useEffect(() => {
        fetchFiles();
    }, [experimentId, extension]);

    const handleFileChange = (event: SelectChangeEvent) => {
        const selectedUrl = event.target.value;
        setSelectedFile(selectedUrl);
        onFileSelected(selectedUrl);
    };

    return (
        <FormControl disabled={disabled} style={{ width: width || "100%" }}>
            <InputLabel id="file-selector-label">Select {extension.toUpperCase()} file</InputLabel>
            <Select
                labelId="file-selector-label"
                value={selectedFile}
                label={`Select ${extension.toUpperCase()} file`}
                onChange={handleFileChange}
            >
                <MenuItem value="">
                    <em>None</em>
                </MenuItem>
                {availableFiles.map((file) => (
                    <MenuItem key={file.name} value={file.url}>
                        {file.name} ({formatFileSize(file.size)})
                    </MenuItem>
                ))}
            </Select>
        </FormControl>
    );
};

export default FileSelector;

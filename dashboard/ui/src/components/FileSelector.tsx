import React, { useState, useEffect, useCallback, useMemo } from "react";

import { FormControl, InputLabel, Select, MenuItem, SelectChangeEvent } from "@mui/material";

import { find_files } from "@/util/api";
import { FileOption } from "@/util/types";
import { formatFileSize } from "@/util/helpers";
import { useNotification } from "@/contexts/useNotification";

export interface FileSelectorProps {
    experimentId: string;
    ext: string | string[];
    title: string;
    onFileSelected: (filePath: string) => void;
    width?: React.CSSProperties["width"];
    ignoreFiles?: string[];
}

const FileSelector = (props: FileSelectorProps) => {
    const { experimentId, ext, onFileSelected, title, width = "100%", ignoreFiles = [] } = props;
    const { showError } = useNotification();
    const [availableFiles, setAvailableFiles] = useState<FileOption[]>([]);
    const [selectedFile, setSelectedFile] = useState<string>("");

    const fetchFiles = useCallback(async () => {
        const { data, error } = await find_files(experimentId, ext);
        if (error) showError(error);
        setAvailableFiles(data || []);
    }, [experimentId, ext, showError]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const filteredFiles = useMemo(
        () => availableFiles.filter((file) => !ignoreFiles.includes(file.name)),
        [availableFiles, ignoreFiles],
    );

    useEffect(() => {
        if (selectedFile && !filteredFiles.some((file) => file.url === selectedFile)) {
            setSelectedFile("");
            onFileSelected("");
        }
    }, [filteredFiles, selectedFile, onFileSelected]);

    const handleFileChange = useCallback(
        (event: SelectChangeEvent) => {
            const selectedUrl = event.target.value;
            setSelectedFile(selectedUrl);
            onFileSelected(selectedUrl);
        },
        [onFileSelected],
    );

    return (
        <FormControl sx={{ width }}>
            <InputLabel id="file-selector-label">{title}</InputLabel>
            <Select labelId="file-selector-label" value={selectedFile} label={title} onChange={handleFileChange}>
                <MenuItem value="">
                    <em>None</em>
                </MenuItem>
                {filteredFiles.map((file) => (
                    <MenuItem key={file.name} value={file.url}>
                        {file.name} ({formatFileSize(file.size)})
                    </MenuItem>
                ))}
            </Select>
        </FormControl>
    );
};

export default FileSelector;

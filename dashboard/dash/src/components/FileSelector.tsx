import React, { useState, useEffect, useCallback, useMemo } from "react";

import { FormControl, InputLabel, Select, MenuItem, SelectChangeEvent } from "@mui/material";

import { find_files } from "@/util/api";
import { FileOption } from "@/util/types";
import { formatFileSize } from "@/util/helpers";

export interface FileSelectorProps {
    experimentId: string;
    ext: string | string[];
    title: string;
    onFileSelected: (filePath: string) => void;
    setErrorMessage?: (message: string) => void;
    width?: React.CSSProperties["width"];
}

const FileSelector = (props: FileSelectorProps) => {
    const { experimentId, ext, onFileSelected, setErrorMessage, title, width = "100%" } = props;
    const [availableFiles, setAvailableFiles] = useState<FileOption[]>([]);
    const [selectedFile, setSelectedFile] = useState<string>("");

    const fetchFiles = useCallback(async () => {
        const { data, error } = await find_files(experimentId, ext);
        if (error && setErrorMessage) setErrorMessage(error);
        setAvailableFiles(data || []);
    }, [experimentId, ext, setErrorMessage]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const menuItems = useMemo(
        () =>
            availableFiles.map((file) => (
                <MenuItem key={file.name} value={file.url}>
                    {file.name} ({formatFileSize(file.size)})
                </MenuItem>
            )),
        [availableFiles]
    );

    const handleFileChange = (event: SelectChangeEvent) => {
        const selectedUrl = event.target.value;
        setSelectedFile(selectedUrl);
        onFileSelected(selectedUrl);
    };

    return (
        <FormControl style={{ width }}>
            <InputLabel id="file-selector-label">{title}</InputLabel>
            <Select labelId="file-selector-label" value={selectedFile} label={title} onChange={handleFileChange}>
                <MenuItem value="">
                    <em>None</em>
                </MenuItem>
                {menuItems}
            </Select>
        </FormControl>
    );
};

export default FileSelector;

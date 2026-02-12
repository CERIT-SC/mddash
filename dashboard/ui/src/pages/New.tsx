import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    Stack,
    Paper,
    Button,
    TextField,
    Typography,
    FormControl,
    FormLabel,
    Tabs,
    Tab,
    FormHelperText,
    CircularProgress,
    InputAdornment,
    IconButton,
    Tooltip,
    Box,
    Collapse,
} from "@mui/material";
import ReplayIcon from "@mui/icons-material/Replay";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";

import Dropzone from "@/components/Dropzone";
import { create_experiment } from "@/util/api";
import { useNotification } from "@/contexts/useNotification";
import { DEFAULT_NOTEBOOKS_REPO } from "@/util/const";

const tabStyles = {
    textTransform: "none",
    borderRadius: 1,
    border: 1,
    color: "text.secondary",
    bgcolor: "background.paper",
    borderColor: "divider",
    "&.Mui-selected": {
        color: "primary.contrastText",
        bgcolor: "primary.main",
        borderColor: "text.primary",
    },
    "&:not(.Mui-selected):hover": {
        bgcolor: "action.hover",
        color: "text.primary",
    },
} as const;

const isValidGitUrl = (url: string): boolean => {
    // SSH format: git@host:owner/repo.git
    if (url.startsWith("git@") && url.includes(":")) {
        return true;
    }
    // HTTPS format
    try {
        const parsed = new URL(url);
        return ["http:", "https:"].includes(parsed.protocol) && Boolean(parsed.host);
    } catch {
        return false;
    }
};

const New = () => {
    const navigate = useNavigate();
    const { showError, showSuccess } = useNotification();

    const [name, setName] = useState("");
    const [type, setType] = useState("");
    const [pdbId, setPdbId] = useState("");
    const [repoUrl, setRepoUrl] = useState("");
    const [files, setFiles] = useState<File[]>([]);
    const [notebooksRepo, setNotebooksRepo] = useState(DEFAULT_NOTEBOOKS_REPO);
    const [accessToken, setAccessToken] = useState("");
    const [showTokenInput, setShowTokenInput] = useState(false);

    // Check if the notebooks repo supports access tokens (HTTPS URLs only, not SSH)
    const isHttpsRepo = notebooksRepo.startsWith("http://") || notebooksRepo.startsWith("https://");

    // Clear token and hide input if switching to SSH or default repo
    const handleNotebooksRepoChange = (value: string) => {
        setNotebooksRepo(value);
        const isHttps = value.startsWith("http://") || value.startsWith("https://");
        if (!isHttps || value === DEFAULT_NOTEBOOKS_REPO) {
            setAccessToken("");
            setShowTokenInput(false);
        }
    };

    const [nameError, setNameError] = useState(false);
    const [typeError, setTypeError] = useState(false);
    const [typeAuxError, setTypeAuxError] = useState(false);
    const [notebooksRepoError, setNotebooksRepoError] = useState(false);
    const [loading, setLoading] = useState(false);

    const validateForm = () => {
        let typeAuxError = false;
        const notebooksInvalid = !isValidGitUrl(notebooksRepo);

        if ((type === "pdb" && !pdbId) || (type === "repo" && !repoUrl) || (type === "file" && files.length === 0))
            typeAuxError = true;

        setNameError(!name);
        setTypeError(!type);
        setTypeAuxError(typeAuxError);
        setNotebooksRepoError(notebooksInvalid);

        if (name && type && !typeAuxError && !notebooksInvalid) return true;

        showError("Please fill in all required fields");
        return false;
    };

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();

        if (loading || !validateForm()) return;

        setLoading(true);

        const formData = new FormData();
        formData.append("experiment-name", name);
        formData.append("type", type);
        formData.append("notebooks-repo", notebooksRepo);
        if (type === "pdb") formData.append("pdb-id", pdbId);
        if (type === "repo") formData.append("repo-url", repoUrl);
        if (type === "file" && files.length > 0) {
            files.forEach((file) => formData.append("simulation-files", file));
        }
        if (accessToken) formData.append("access-token", accessToken);

        const { data, error } = await create_experiment(formData);

        if (error) {
            showError(error);
            setLoading(false);
            return;
        }

        console.log("Experiment created:", data);
        showSuccess("Experiment created successfully!");
        setLoading(false);
        navigate(`/${data!.id}/wizard`);
    };

    const handleTypeChange = (_: React.SyntheticEvent, newType: string | false) => {
        if (typeof newType !== "string") return;
        setType(newType);
        setPdbId("");
        setRepoUrl("");
        setFiles([]);
    };

    return (
        <>
            <Typography variant="h1" gutterBottom align="center">
                New Experiment
            </Typography>

            <Paper elevation={2} sx={{ maxWidth: 640, mx: "auto" }}>
                <Stack component="form" autoComplete="off" onSubmit={handleSubmit} spacing={4} p={4} sx={{ width: 1 }}>
                    <TextField
                        name="experiment-name"
                        label="Name"
                        variant="outlined"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        error={nameError}
                    />

                    <FormControl error={typeError || typeAuxError}>
                        <FormLabel>Initial Data</FormLabel>
                        <Tabs
                            value={type || false}
                            onChange={handleTypeChange}
                            aria-label="Initial data source"
                            variant="fullWidth"
                            TabIndicatorProps={{ style: { display: "none" } }}
                            sx={{ mt: 1 }}
                        >
                            <Tab value="file" label="Upload Files" disableRipple sx={tabStyles} />
                            <Tab value="pdb" label="PDB ID" disableRipple sx={tabStyles} />
                            <Tab value="repo" label="Repository URL" disableRipple sx={tabStyles} />
                        </Tabs>
                        {(typeError || typeAuxError) && (
                            <FormHelperText>Select a source and fill its required details.</FormHelperText>
                        )}
                    </FormControl>

                    {type === "pdb" && (
                        <TextField
                            id="pdb-id"
                            label="PDB ID"
                            variant="outlined"
                            value={pdbId}
                            onChange={(e) => setPdbId(e.target.value)}
                            error={typeAuxError}
                        />
                    )}
                    {type === "repo" && (
                        <TextField
                            id="repo-url"
                            label="Repository URL"
                            variant="outlined"
                            value={repoUrl}
                            onChange={(e) => setRepoUrl(e.target.value)}
                            error={typeAuxError}
                        />
                    )}
                    {type === "file" && <Dropzone inputName="simulation-files" onFilesChange={setFiles} />}

                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                        <TextField
                            id="notebooks-repo"
                            label="Notebooks Repository"
                            variant="outlined"
                            value={notebooksRepo}
                            onChange={(e) => handleNotebooksRepoChange(e.target.value)}
                            error={notebooksRepoError}
                            helperText={
                                notebooksRepoError
                                    ? "Enter a valid git repository"
                                    : "Git repository containing setup and analysis notebooks"
                            }
                            slotProps={{
                                input: {
                                    endAdornment: notebooksRepo !== DEFAULT_NOTEBOOKS_REPO && (
                                        <InputAdornment position="end">
                                            <Tooltip title="Reset to default">
                                                <IconButton
                                                    edge="end"
                                                    onClick={() => handleNotebooksRepoChange(DEFAULT_NOTEBOOKS_REPO)}
                                                    size="small"
                                                    aria-label="Reset notebooks repo to default"
                                                >
                                                    <ReplayIcon />
                                                </IconButton>
                                            </Tooltip>
                                        </InputAdornment>
                                    ),
                                },
                            }}
                        />

                        {notebooksRepo !== DEFAULT_NOTEBOOKS_REPO && isHttpsRepo && (
                            <Box>
                                <Box
                                    sx={{
                                        cursor: "pointer",
                                        display: "inline-block",
                                    }}
                                    onClick={() => setShowTokenInput(!showTokenInput)}
                                >
                                    <Typography
                                        variant="body2"
                                        color="text.secondary"
                                        sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}
                                    >
                                        {showTokenInput ? (
                                            <ExpandLessIcon fontSize="small" />
                                        ) : (
                                            <ExpandMoreIcon fontSize="small" />
                                        )}
                                        {showTokenInput ? "Hide access token" : "Provide access token"}
                                    </Typography>
                                </Box>
                                <Collapse in={showTokenInput}>
                                    <TextField
                                        id="access-token"
                                        label="Git Access Token"
                                        type="password"
                                        variant="outlined"
                                        value={accessToken}
                                        onChange={(e) => setAccessToken(e.target.value)}
                                        placeholder="e.g. ghp_xxxxx, glpat_xxxxx, github_pat_xxxxx"
                                        helperText="Required for private HTTPS repositories. Not applicable for SSH URLs. Only used for cloning, not stored."
                                        sx={{ mt: 1 }}
                                        fullWidth
                                    />
                                </Collapse>
                            </Box>
                        )}
                    </Box>

                    <Button
                        variant="contained"
                        type="submit"
                        disabled={loading}
                        startIcon={loading ? <CircularProgress size={20} color="inherit" /> : null}
                        sx={{ alignSelf: "flex-start" }}
                    >
                        {loading ? "Creating..." : "Create Experiment"}
                    </Button>
                </Stack>
            </Paper>
        </>
    );
};

export default New;

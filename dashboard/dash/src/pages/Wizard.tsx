import { useParams } from "react-router-dom";
import { Paper, Typography, CircularProgress } from "@mui/material";
import { useEffect, useState } from "react";

import WizardStepper from "../components/Wizard/Stepper";
import { Experiment } from "../util/types";
import { get_experiment } from "../util/api";
import ErrorMessage from "../components/ErrorMessage";

const Wizard = () => {
    const { id } = useParams<{ id: string }>();

    const [experiment, setExperiment] = useState<Experiment | null>(null);
    const [errorMessage, setErrorMessage] = useState<string>("");

    const getExperiment = async () => {
        if (!id) return;

        const { data, error } = await get_experiment(id);
        setErrorMessage(error || "");
        setExperiment(data || null);
    };

    useEffect(() => {
        getExperiment();
    }, []);

    return (
        <div>
            <Typography variant="h1">Wizard</Typography>

            <Typography variant="h4" sx={{ textAlign: "center" }}>
                {experiment ? experiment.name : "Loading..."}
            </Typography>

            {errorMessage && <ErrorMessage message={errorMessage} />}

            {(experiment && (
                <Paper elevation={2} sx={{ p: 4, mt: 4 }}>
                    <WizardStepper
                        experiment={experiment}
                        setExperiment={setExperiment}
                        setErrorMessage={setErrorMessage}
                    />
                </Paper>
            )) || (
                <div style={{ display: "flex", justifyContent: "center", marginTop: "20px" }}>
                    <CircularProgress />
                </div>
            )}
        </div>
    );
};

export default Wizard;

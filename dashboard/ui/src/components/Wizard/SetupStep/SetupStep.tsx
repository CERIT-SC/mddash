import { useState } from "react";

import { Stack, Button, Typography } from "@mui/material";
import { SkipNext } from "@mui/icons-material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { formatDateTime } from "@/util/helpers";
import ConfirmDialog from "@/components/ConfirmDialog";
import NotebookController from "./NotebookController";

const SetupStep = (props: WizardStepProps) => {
    const { experiment, nextStep } = props;
    const [nextStepDialog, setNextStepDialog] = useState(false);

    return (
        <Stack direction="column" alignItems="center" spacing={5}>
            <Stack direction="column" width="90%">
                <Stack direction="row" justifyContent="space-between">
                    <Typography variant="h3">Experiment Details</Typography>
                    {experiment.step === 0 && (
                        <Button
                            variant="outlined"
                            color="error"
                            startIcon={<SkipNext />}
                            onClick={() => setNextStepDialog(true)}
                        >
                            Skip Setup
                        </Button>
                    )}
                </Stack>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body1">Creation Date:</Typography>
                    <Typography variant="body1" color="text.disabled">
                        {formatDateTime(experiment.created_at)}
                    </Typography>
                </Stack>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body1">Creation Method:</Typography>
                    <Typography variant="body1" color="text.disabled">
                        {experiment.source_message}
                    </Typography>
                </Stack>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body1">Notebook Repository:</Typography>
                    <Typography variant="body1" color="text.disabled">
                        {experiment.notebook_repo || "N/A"}
                    </Typography>
                </Stack>
            </Stack>

            <NotebookController experimentId={experiment.id} />

            <ConfirmDialog
                open={nextStepDialog}
                setOpen={setNextStepDialog}
                title="Complete Setup?"
                message="Are you sure you want to proceed to the next step? Setup doesn't appear to be complete in the notebook. Stuff may break later."
                onConfirm={nextStep}
            />
        </Stack>
    );
};

export default SetupStep;

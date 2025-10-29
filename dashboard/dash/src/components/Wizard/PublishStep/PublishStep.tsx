import { useState, useCallback, useMemo } from "react";
import { Box, Button } from "@mui/material";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { publish_experiment } from "@/util/api";
import { useNotification } from "@/contexts/NotificationContext";

const MDREPO_BASE_URL = "https://mdrepo.eu";

const PublishStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const { showError } = useNotification();
    const [loading, setLoading] = useState(false);

    const isPublished = experiment.mdrepo_id !== null;

    const handlePublishClick = useCallback(async () => {
        try {
            setLoading(true);

            if (isPublished) {
                window.location.href = `${MDREPO_BASE_URL}/experiments/${experiment.mdrepo_id}/edit`;
                return;
            }

            const { data, error } = await publish_experiment(experiment.id);

            if (error) {
                showError(error);
                return;
            }

            if (!data) {
                showError("Invalid response from server.");
                return;
            }

            experiment.mdrepo_id = data.id;
            window.location.href = data.links.edit_html;
        } catch (e) {
            showError("Invalid response from server.");
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, [experiment, isPublished, showError]);

    const buttonText = useMemo(() => {
        return isPublished ? "View" : "Publish";
    }, [isPublished]);

    return (
        <Box sx={{ p: 4, display: "flex", flexDirection: "column", alignItems: "center" }}>
            <Button variant="contained" color="primary" onClick={handlePublishClick} disabled={loading}>
                {buttonText}
            </Button>
        </Box>
    );
};

export default PublishStep;

import { useState } from "react";
import { Box, Button } from "@mui/material";

import { WizardStepProps } from "./Stepper"
import { publish_experiment } from "../../util/api";

const WizardPublish = (props: WizardStepProps) => {
    const { experiment, setErrorMessage } = props;
    const [loading, setLoading] = useState(false);

    const publishExperiment = async () => {
        try {
            setLoading(true);
            if (experiment.mdrepo_id != null) {
                window.location.href = `https://mdrepo.eu/experiments/${experiment.mdrepo_id}/edit`;
                return;
            }
    
            const { data, error } = await publish_experiment(experiment.id);
            setErrorMessage(error || '');
            if (error) return;
    
            experiment.mdrepo_id = data.id;
            window.location.href = data.links.edit_html;
        }
        catch (e) {
            setErrorMessage('Invalid response from server.');
            console.error(e);
        }
        finally {
            setLoading(false);
        }
    };

    return (
        <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Button variant="contained" color="primary" onClick={publishExperiment} loading={loading}>Publish</Button>
        </Box>
    );
}

export default WizardPublish;

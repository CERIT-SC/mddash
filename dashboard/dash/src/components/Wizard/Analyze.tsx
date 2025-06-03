import { useEffect } from "react";

import { Stack } from "@mui/material";

import { WizardStepperProps } from "./Stepper";
import { initViewerUI, loadStructure } from "../MolStar";

const CONTAINER_NAME = "molstar-container";

const WizardAnalyze = (props: WizardStepperProps) => {
    console.log(props);

    async function init() {
        const plugin = await initViewerUI(CONTAINER_NAME, {
            spec: {
                layout: {
                    initial: {
                        isExpanded: false,
                        showControls: false,
                        controlsDisplay: "reactive",
                    },
                },
                behaviors: [],
            },
        });

        // TODO: load actual file from experiment
        await loadStructure(plugin, "https://models.rcsb.org/4hhb.bcif", { isBinary: true });
    }

    useEffect(() => {
        init().catch((error) => {
            console.error("Error initializing Mol* viewer:", error);
        });
    }, []);

    return (
        <Stack
            alignContent={"center"}
            justifyContent="center"
            alignItems="center"
            sx={{ width: "100%", height: "100%" }}
        >
            <div
                id={CONTAINER_NAME}
                style={{
                    width: "800px",
                    height: "600px",
                    position: "relative",
                }}
            />
        </Stack>
    );
};

export default WizardAnalyze;

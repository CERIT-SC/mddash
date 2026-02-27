import React, { useState, useEffect, useRef } from "react";
import { createRoot, Root } from "react-dom/client";

import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import "molstar/lib/mol-plugin-ui/skin/light.scss";
import { DefaultPluginUISpec, PluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin";
import { StateTransforms } from "molstar/lib/mol-plugin-state/transforms";
import { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory";
import { BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates";

interface MolStarProps {
    width?: React.CSSProperties["width"];
    height?: React.CSSProperties["height"];
    pdbId?: string;
    structureUrl?: string;
    structureFormat?: BuiltInTrajectoryFormat;
    coordsUrl?: string;
    coordsFormat?: BuiltInCoordinatesFormat;
}

export default function MolStar(props: MolStarProps) {
    const { width = "500px", height = "500px", pdbId, structureUrl, structureFormat, coordsUrl, coordsFormat } = props;

    const [loading, setLoading] = useState(true);
    const pluginRef = useRef<PluginUIContext | null>(null);
    const rootRef = useRef<Root | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const isMountedRef = useRef(true);

    useEffect(() => {
        isMountedRef.current = true;
        let plugin: PluginUIContext | null = null;
        let root: Root | null = null;

        const init = async () => {
            if (!containerRef.current || !isMountedRef.current) return;

            try {
                setLoading(true);

                const spec: PluginUISpec = {
                    ...DefaultPluginUISpec(),
                    layout: {
                        initial: {
                            isExpanded: false,
                            showControls: false,
                            controlsDisplay: "reactive",
                        },
                    },
                };

                plugin = new PluginUIContext(spec);
                await plugin.init();

                if (!isMountedRef.current) {
                    plugin.dispose();
                    return;
                }

                containerRef.current.innerHTML = "";
                root = createRoot(containerRef.current);
                root.render(<Plugin plugin={plugin} />);

                pluginRef.current = plugin;
                rootRef.current = root;

                if (coordsUrl && structureUrl) {
                    await loadTrajectoryWithCoordinates(plugin, {
                        structureUrl,
                        structureFormat: structureFormat || "gro",
                        coordsUrl,
                        coordsFormat: coordsFormat || "xtc",
                    });
                } else if (structureUrl) {
                    await loadSingleStructure(plugin, {
                        url: structureUrl,
                        format: structureFormat || "pdb",
                    });
                } else if (pdbId) {
                    await loadSingleStructure(plugin, {
                        url: `https://models.rcsb.org/${pdbId.toLowerCase()}.bcif`,
                        format: "mmcif",
                        isBinary: true,
                    });
                } else {
                    throw new Error("No structure source provided (pdbId, structureUrl, or coordsUrl+structureUrl)");
                }
            } catch (error) {
                if (isMountedRef.current) {
                    console.error("MolStar initialization error:", error);
                    const errorMessage = error instanceof Error ? error.message : String(error);
                    toast.error(errorMessage);
                }
            } finally {
                if (isMountedRef.current) {
                    setLoading(false);
                }
            }
        };

        init();

        return () => {
            isMountedRef.current = false;
            if (pluginRef.current) {
                pluginRef.current.dispose();
                pluginRef.current = null;
            }
            if (rootRef.current) {
                rootRef.current.unmount();
                rootRef.current = null;
            }
        };
    }, [pdbId, structureUrl, structureFormat, coordsUrl, coordsFormat]);

    return (
        <div style={{ width, height, position: "relative", zIndex: 10 }}>
            {loading && (
                <div
                    style={{
                        position: "absolute",
                        top: "50%",
                        left: "50%",
                        transform: "translate(-50%, -50%)",
                        zIndex: 11,
                    }}
                >
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            )}
            <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        </div>
    );
}

async function loadSingleStructure(
    plugin: PluginUIContext,
    options: {
        url: string;
        format: BuiltInTrajectoryFormat | "mmcif";
        isBinary?: boolean;
    },
) {
    const { url, format, isBinary = format !== "pdb" && format !== "gro" } = options;

    const data = await plugin.builders.data.download({ url, isBinary }, { state: { isGhost: true } });

    if (!data || !data.isOk) {
        throw new Error(`Failed to download structure from ${url}`);
    }

    const trajectory = await plugin.builders.structure.parseTrajectory(data, format);

    if (!trajectory || !trajectory.isOk) {
        throw new Error(`Failed to parse structure file as ${format}`);
    }

    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");
}

async function loadTrajectoryWithCoordinates(
    plugin: PluginUIContext,
    options: {
        structureUrl: string;
        structureFormat: BuiltInTrajectoryFormat;
        coordsUrl: string;
        coordsFormat: BuiltInCoordinatesFormat;
    },
) {
    const { structureUrl, structureFormat, coordsUrl, coordsFormat } = options;
    const state = plugin.state.data;

    const structureIsBinary = structureFormat !== "pdb" && structureFormat !== "gro";
    const coordsIsBinary = coordsFormat !== "lammpstrj";

    const structureData = await plugin.builders.data.download(
        { url: structureUrl, isBinary: structureIsBinary },
        { state: { isGhost: true } },
    );

    if (!structureData || !structureData.isOk) {
        throw new Error(`Failed to download topology file from ${structureUrl}`);
    }

    const structureTrajectory = await plugin.builders.structure.parseTrajectory(structureData, structureFormat);

    if (!structureTrajectory || !structureTrajectory.isOk) {
        throw new Error(`Failed to parse topology file as ${structureFormat}`);
    }

    const model = await plugin.builders.structure.createModel(structureTrajectory);

    if (!model || !model.isOk) {
        throw new Error("Failed to create model from topology");
    }

    const coordsData = await plugin.builders.data.download(
        { url: coordsUrl, isBinary: coordsIsBinary },
        { state: { isGhost: true } },
    );

    if (!coordsData || !coordsData.isOk) {
        throw new Error(`Failed to download coordinates file from ${coordsUrl}`);
    }

    let coordsTransform;
    switch (coordsFormat) {
        case "xtc":
            coordsTransform = StateTransforms.Model.CoordinatesFromXtc;
            break;
        case "dcd":
            coordsTransform = StateTransforms.Model.CoordinatesFromDcd;
            break;
        case "trr":
            coordsTransform = StateTransforms.Model.CoordinatesFromTrr;
            break;
        case "nctraj":
            coordsTransform = StateTransforms.Model.CoordinatesFromNctraj;
            break;
        case "lammpstrj":
            coordsTransform = StateTransforms.Model.CoordinatesFromLammpstraj;
            break;
        default:
            throw new Error(`Unsupported coordinates format: ${coordsFormat}`);
    }

    const coords = await state
        .build()
        .to(coordsData)
        .apply(coordsTransform, {}, { state: { isGhost: true } })
        .commit({ revertOnError: true });

    if (!coords || !coords.isOk) {
        throw new Error(`Failed to parse coordinates file as ${coordsFormat}`);
    }

    const trajectory = await state
        .build()
        .toRoot()
        .apply(
            StateTransforms.Model.TrajectoryFromModelAndCoordinates,
            {
                modelRef: model.ref,
                coordinatesRef: coords.ref,
            },
            { dependsOn: [model.ref, coords.ref] },
        )
        .commit({ revertOnError: true });

    if (!trajectory || !trajectory.isOk) {
        throw new Error("Failed to create trajectory from topology and coordinates");
    }

    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");
}

import React, { useState, useEffect, useRef } from "react";
import { createRoot, Root } from "react-dom/client";

import { CircularProgress } from "@mui/material";

import "molstar/lib/mol-plugin-ui/skin/light.scss";
import { DefaultPluginUISpec, PluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin";
import { TrajectoryFromModelAndCoordinates } from "molstar/lib/mol-plugin-state/transforms/model";
import { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory";
import { BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates";
import { useNotification } from "@/contexts/NotificationContext";

export const initViewerUI = async (element: string | HTMLDivElement, options?: { spec?: PluginUISpec }) => {
    const parent = typeof element === "string" ? (document.getElementById(element)! as HTMLDivElement) : element;
    const spec = { ...DefaultPluginUISpec(), ...options?.spec };
    const plugin = new PluginUIContext(spec);
    await plugin.init();

    // Clear existing content first
    parent.innerHTML = "";

    const root = createRoot(parent);
    root.render(<Plugin plugin={plugin} />);
    return { plugin, root };
};

export const loadStructure = async (
    plugin: PluginUIContext,
    url: string,
    options?: { format?: string; isBinary?: boolean }
) => {
    const data = await plugin.builders.data.download({
        url,
        isBinary: options?.isBinary ?? false,
    });
    const trajectory = await plugin.builders.structure.parseTrajectory(data, options?.format ?? ("mmcif" as any));
    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");
    return trajectory;
};

interface LoadTrajectoryParams {
    plugin: PluginUIContext;
    modelUrl: string;
    modelFormat?: BuiltInTrajectoryFormat;
    modelIsBinary?: boolean;
    modelLabel?: string;
    coordsUrl: string;
    coordsFormat?: BuiltInCoordinatesFormat;
    coordsIsBinary?: boolean;
    coordsLabel?: string;
    preset?: "default" | "all-models";
}

export const loadTrajectory = async (params: LoadTrajectoryParams) => {
    const {
        plugin,
        modelUrl,
        modelFormat = "gro",
        modelIsBinary = false,
        modelLabel,
        coordsUrl,
        coordsFormat = "xtc",
        coordsIsBinary = true,
        coordsLabel,
        preset = "default",
    } = params;

    // Load topology/structure data
    const modelData = await plugin.builders.data.download({
        url: modelUrl,
        isBinary: modelIsBinary,
        label: modelLabel,
    });

    // Parse as trajectory for standard formats
    const modelTrajectory = await plugin.builders.structure.parseTrajectory(modelData, modelFormat as any);
    let model = await plugin.builders.structure.createModel(modelTrajectory);

    // Load coordinate trajectory data
    const coordData = await plugin.builders.data.download({
        url: coordsUrl,
        isBinary: coordsIsBinary,
        label: coordsLabel,
    });

    const coordProvider = plugin.dataFormats.get(coordsFormat);
    if (!coordProvider) {
        throw new Error(`Unknown coordinates format: ${coordsFormat}`);
    }
    const coords = await coordProvider.parse(plugin, coordData);

    // Create trajectory from model and coordinates
    const coordsTrajectory = await plugin
        .build()
        .toRoot()
        .apply(
            TrajectoryFromModelAndCoordinates,
            {
                modelRef: model.ref,
                coordinatesRef: coords.ref,
            },
            { dependsOn: [model.ref, coords.ref] }
        )
        .commit();

    // Apply default preset to create hierarchy
    const presetResult = await plugin.builders.structure.hierarchy.applyPreset(coordsTrajectory, preset);

    return { model, coords, coordsTrajectory, preset: presetResult };
};

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

    const { showError } = useNotification();
    const [loading, setLoading] = useState(true);
    const pluginRef = useRef<PluginUIContext | null>(null);
    const rootRef = useRef<Root | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const containerId = useRef(`molstar-container-${Math.random().toString(36).substr(2, 9)}`);

    const cleanup = () => {
        if (pluginRef.current) {
            pluginRef.current.dispose();
            pluginRef.current = null;
        }
        if (rootRef.current) {
            rootRef.current.unmount();
            rootRef.current = null;
        }
    };

    const init = async () => {
        if (!containerRef.current) return;

        try {
            setLoading(true);

            // Cleanup previous instance
            cleanup();

            const { plugin, root } = await initViewerUI(containerRef.current, {
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

            pluginRef.current = plugin;
            rootRef.current = root;

            // Add validation for URLs
            if (coordsUrl && structureUrl) {
                await loadTrajectory({
                    plugin,
                    modelUrl: structureUrl,
                    coordsUrl: coordsUrl,
                    modelFormat: structureFormat,
                    coordsFormat: coordsFormat,
                    modelIsBinary: structureFormat !== "pdb",
                });
            } else if (structureUrl) {
                await loadStructure(plugin, structureUrl, {
                    format: structureFormat,
                    isBinary: structureFormat !== "pdb",
                });
            } else if (pdbId) {
                await loadStructure(plugin, `https://models.rcsb.org/${pdbId.toLowerCase()}.bcif`, {
                    isBinary: true,
                });
            }
        } catch (error) {
            console.error("Error initializing Mol* viewer:", error);
            showError(`Error initializing Mol* viewer: ${error}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        init();

        // Cleanup on unmount
        return cleanup;
    }, [structureUrl, coordsUrl, pdbId]);

    return (
        <div style={{ width, height, position: "relative", zIndex: 10 }}>
            {loading && (
                <div
                    style={{
                        position: "absolute",
                        top: "50%",
                        left: "50%",
                        transform: "translate(-50%, -50%)",
                        zIndex: 10,
                    }}
                >
                    <CircularProgress />
                </div>
            )}
            <div ref={containerRef} id={containerId.current} style={{ width: "100%", height: "100%" }} />
        </div>
    );
}

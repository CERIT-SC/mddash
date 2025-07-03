import React, { useState, useEffect, useRef } from "react";
import { createRoot, Root } from "react-dom/client";

import { CircularProgress } from "@mui/material";

import "molstar/lib/mol-plugin-ui/skin/light.scss";
import { DefaultPluginUISpec, PluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin";
import { TrajectoryFromModelAndCoordinates } from "molstar/lib/mol-plugin-state/transforms/model";

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
    structureUrl: string;
    trajectoryUrl: string;
    structureFormat?: string;
    trajectoryFormat?: string;
    structureIsBinary?: boolean;
    trajectoryIsBinary?: boolean;
    structureLabel?: string;
    trajectoryLabel?: string;
    preset?: "default" | "all-models";
}

export const loadTrajectory = async (params: LoadTrajectoryParams) => {
    const {
        plugin,
        structureUrl,
        trajectoryUrl,
        structureFormat = "gro",
        trajectoryFormat = "xtc",
        structureIsBinary = false,
        trajectoryIsBinary = true,
        structureLabel,
        trajectoryLabel,
        preset = "default",
    } = params;

    let model;

    // Load topology/structure data
    const structureData = await plugin.builders.data.download({
        url: structureUrl,
        isBinary: structureIsBinary,
        label: structureLabel,
    });

    // Check if we should parse as trajectory or use topology provider
    if (structureFormat === "pdb" || structureFormat === "mmcif" || structureFormat === "cif") {
        // Parse as trajectory for standard formats
        const trajectory = await plugin.builders.structure.parseTrajectory(structureData, structureFormat as any);
        model = await plugin.builders.structure.createModel(trajectory);
    } else {
        // Use data format provider for topology formats like GRO
        const provider = plugin.dataFormats.get(structureFormat);
        if (!provider) {
            throw new Error(`Unknown structure format: ${structureFormat}`);
        }
        const parsed = await provider.parse(plugin, structureData);
        model = parsed.topology;
    }

    // Load coordinate trajectory data
    const trajectoryData = await plugin.builders.data.download({
        url: trajectoryUrl,
        isBinary: trajectoryIsBinary,
        label: trajectoryLabel,
    });

    const coordProvider = plugin.dataFormats.get(trajectoryFormat);
    if (!coordProvider) {
        throw new Error(`Unknown trajectory format: ${trajectoryFormat}`);
    }
    const coords = await coordProvider.parse(plugin, trajectoryData);

    // Create trajectory from model and coordinates
    const trajectory = await plugin
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
    const presetResult = await plugin.builders.structure.hierarchy.applyPreset(trajectory, preset);

    return { model, coords, trajectory, preset: presetResult };
};

interface MolStarProps {
    width?: React.CSSProperties["width"];
    height?: React.CSSProperties["height"];
    pdbId?: string;
    structureUrl?: string;
    structureFormat?: "gro" | "pdb" | "cif" | "mmcif" | "bcif" | "sfd" | "mol" | "mol2";
    trajectoryUrl?: string;
    trajectoryFormat?: "xtc" | "trr" | "dcd";
    setErrorMessage?: (message: string) => void;
}

export default function MolStar(props: MolStarProps) {
    const {
        width = "500px",
        height = "500px",
        pdbId,
        structureUrl,
        structureFormat,
        trajectoryUrl,
        trajectoryFormat,
        setErrorMessage,
    } = props;

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
            setErrorMessage?.("");

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
            if (trajectoryUrl && structureUrl) {
                await loadTrajectory({
                    plugin,
                    structureUrl,
                    trajectoryUrl,
                    structureFormat,
                    trajectoryFormat,
                    structureIsBinary: structureFormat !== "pdb",
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
            if (setErrorMessage) {
                setErrorMessage(`Error initializing Mol* viewer: ${error}`);
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        init();

        // Cleanup on unmount
        return cleanup;
    }, [structureUrl, trajectoryUrl, pdbId]);

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

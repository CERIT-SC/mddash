// modified version of https://molstar.org/docs/plugin/custom-library/

import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";

import { CircularProgress } from "@mui/material";

import "molstar/lib/mol-plugin-ui/skin/light.scss";
import { DefaultPluginUISpec, PluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin";

export const initViewerUI = async (element: string | HTMLDivElement, options?: { spec?: PluginUISpec }) => {
    const parent = typeof element === "string" ? (document.getElementById(element)! as HTMLDivElement) : element;
    const spec = { ...DefaultPluginUISpec(), ...options?.spec };
    const plugin = new PluginUIContext(spec);
    await plugin.init();
    createRoot(parent).render(<Plugin plugin={plugin} />);
    return plugin;
};

export const loadStructure = async (
    plugin: PluginUIContext,
    url: string,
    options?: { format?: string; isBinary?: boolean }
) => {
    const data = await plugin.builders.data.download({ url, isBinary: options?.isBinary });
    const trajectory = await plugin.builders.structure.parseTrajectory(data, options?.format ?? ("mmcif" as any));
    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");
};

export const loadTrajectory = async (
    plugin: PluginUIContext,
    structureUrl: string, // .gro, .pdb, .tpr
    trajectoryUrl: string, // .xtc, .trr
    options?: {
        structureFormat?: string;
        trajectoryFormat?: string;
        isBinary?: boolean;
    }
) => {
    // Load structure file (topology)
    const structureData = await plugin.builders.data.download({
        url: structureUrl,
        isBinary: options?.isBinary ?? false,
    });
    const structure = await plugin.builders.structure.parseTrajectory(
        structureData,
        (options?.structureFormat ?? "gro") as any
    );

    // Load trajectory file
    const trajectoryData = await plugin.builders.data.download({
        url: trajectoryUrl,
        isBinary: true,
    });
    const trajectory = await plugin.builders.structure.parseTrajectory(
        trajectoryData,
        (options?.trajectoryFormat ?? "xtc") as any
    );

    // Combine structure + trajectory
    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");

    return { structure, trajectory };
};

interface MolStarProps {
    width?: React.CSSProperties["width"];
    height?: React.CSSProperties["height"];
    pdbId?: string;
    structureUrl?: string;
    trajectoryUrl?: string;
    structureFormat?: "gro" | "pdb" | "tpr";
    trajectoryFormat?: "xtc" | "trr" | "dcd";
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
    } = props;
    const [loading, setLoading] = useState(true);
    const containerId = `molstar-container-${Math.random().toString(36).substr(2, 9)}`;

    const init = async () => {
        try {
            const plugin = await initViewerUI(containerId, {
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

            if (trajectoryUrl && structureUrl) {
                await loadTrajectory(plugin, structureUrl, trajectoryUrl, {
                    structureFormat: structureFormat ?? "gro",
                    trajectoryFormat: trajectoryFormat ?? "xtc",
                    isBinary: structureFormat !== "pdb", // Most formats except PDB are binary
                });
            } else if (structureUrl) {
                await loadStructure(plugin, structureUrl, { isBinary: true });
            } else if (pdbId) {
                await loadStructure(plugin, `https://models.rcsb.org/${pdbId.toLowerCase()}.bcif`, { isBinary: true });
            }
        } catch (error) {
            console.error("Error initializing Mol* viewer:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        init();
    }, []);

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
            <div id={containerId} style={{ width: "100%", height: "100%" }} />
        </div>
    );
}

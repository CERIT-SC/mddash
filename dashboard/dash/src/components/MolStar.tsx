// stolen from https://molstar.org/docs/plugin/custom-library/

import { createRoot } from "react-dom/client";
import "molstar/lib/mol-plugin-ui/skin/light.scss";

import { DefaultPluginUISpec, PluginUISpec } from "molstar/lib/mol-plugin-ui/spec";
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin";

export async function initViewerUI(element: string | HTMLDivElement, options?: { spec?: PluginUISpec }) {
    const parent = typeof element === "string" ? (document.getElementById(element)! as HTMLDivElement) : element;
    const spec = { ...DefaultPluginUISpec(), ...options?.spec };
    const plugin = new PluginUIContext(spec);
    await plugin.init();

    createRoot(parent).render(<Plugin plugin={plugin} />);

    return plugin;
}

export async function loadStructure(
    plugin: PluginUIContext,
    url: string,
    options?: { format?: string; isBinary?: boolean }
) {
    const data = await plugin.builders.data.download({ url, isBinary: options?.isBinary });
    const trajectory = await plugin.builders.structure.parseTrajectory(data, options?.format ?? ("mmcif" as any));
    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default");
}

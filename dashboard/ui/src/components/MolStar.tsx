import React, { useEffect, useRef, useState } from "react"

import { Loader2 } from "lucide-react"
import { createRoot, type Root } from "react-dom/client"
import { toast } from "sonner"

import "molstar/lib/mol-plugin-ui/skin/light.scss"

import { StateTransforms } from "molstar/lib/mol-plugin-state/transforms"
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context"
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin"
import { DefaultPluginUISpec, type PluginUISpec } from "molstar/lib/mol-plugin-ui/spec"

type StructureFormat = string
type CoordsFormat = string

/** Map file extensions to MolStar structure/topology format IDs. */
const STRUCTURE_FORMAT_MAP: Record<string, StructureFormat> = {
  pdb: "pdb",
  gro: "gro",
  mmcif: "mmcif",
  cifcore: "cifCore",
  pdbqt: "pdbqt",
  xyz: "xyz",
  mol: "mol",
  sdf: "sdf",
  mol2: "mol2",
  psf: "psf",
  prmtop: "prmtop",
  parm7: "prmtop",
  top: "top",
}

/** Map file extensions to MolStar coordinates format IDs. */
const COORDS_FORMAT_MAP: Record<string, CoordsFormat> = {
  xtc: "xtc",
  trr: "trr",
  dcd: "dcd",
  nc: "nctraj",
  nctraj: "nctraj",
  lammpstrj: "lammpstrj",
}

/** Resolve a file extension to a MolStar structure/topology format. */
export function resolveStructureFormat(filename: string): StructureFormat {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  return STRUCTURE_FORMAT_MAP[ext] ?? "pdb"
}

/** Resolve a file extension to a MolStar coordinates format. */
export function resolveCoordsFormat(filename: string): CoordsFormat {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  return COORDS_FORMAT_MAP[ext] ?? "xtc"
}

interface MolStarProps {
  width?: React.CSSProperties["width"]
  height?: React.CSSProperties["height"]
  pdbId?: string
  structureUrl?: string
  structureFormat?: StructureFormat
  coordsUrl?: string
  coordsFormat?: CoordsFormat
}

export default function MolStar(props: MolStarProps) {
  const { width = "500px", height = "500px", pdbId, structureUrl, structureFormat, coordsUrl, coordsFormat } = props

  const [loading, setLoading] = useState(true)
  const pluginRef = useRef<PluginUIContext | null>(null)
  const rootRef = useRef<Root | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    let plugin: PluginUIContext | null = null
    let root: Root | null = null
    let cancelled = false

    const init = async () => {
      if (!containerRef.current || !isMountedRef.current) return

      try {
        setLoading(true)

        const spec: PluginUISpec = {
          ...DefaultPluginUISpec(),
          layout: {
            initial: {
              isExpanded: false,
              showControls: false,
              controlsDisplay: "reactive",
            },
          },
        }

        plugin = new PluginUIContext(spec)
        await plugin.init()

        if (!isMountedRef.current || cancelled) {
          plugin.dispose()
          return
        }

        // Defer DOM reset so any in-progress React 19 unmount from the
        // Strict Mode double-invocation finishes before we reuse the container.
        await new Promise<void>((resolve) => setTimeout(resolve, 0))

        if (!isMountedRef.current || cancelled) {
          plugin.dispose()
          return
        }

        const container = containerRef.current
        container.innerHTML = ""
        root = createRoot(container)
        root.render(<Plugin plugin={plugin} />)

        pluginRef.current = plugin
        rootRef.current = root

        if (structureUrl && coordsUrl) {
          await loadStructureWithCoordinates(plugin, {
            structureUrl,
            structureFormat: structureFormat ?? "pdb",
            coordsUrl,
            coordsFormat: coordsFormat ?? "xtc",
          })
        } else if (structureUrl) {
          await loadSingleStructure(plugin, {
            url: structureUrl,
            format: structureFormat ?? "pdb",
          })
        } else if (pdbId) {
          await loadSingleStructure(plugin, {
            url: `https://models.rcsb.org/${pdbId.toLowerCase()}.bcif`,
            format: "mmcif",
            isBinary: true,
          })
        } else {
          throw new Error("No structure source provided (pdbId, structureUrl, or structureUrl+coordsUrl)")
        }
      } catch (error) {
        if (isMountedRef.current && !cancelled) {
          console.error("MolStar initialization error:", error)
          const errorMessage = error instanceof Error ? error.message : String(error)
          toast.error(errorMessage)
        }
      } finally {
        if (isMountedRef.current && !cancelled) {
          setLoading(false)
        }
      }
    }

    init()

    return () => {
      cancelled = true
      isMountedRef.current = false
      if (pluginRef.current) {
        pluginRef.current.dispose()
        pluginRef.current = null
      }
      if (rootRef.current) {
        rootRef.current.unmount()
        rootRef.current = null
      }
    }
  }, [pdbId, structureUrl, structureFormat, coordsUrl, coordsFormat])

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
          <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
        </div>
      )}
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
    </div>
  )
}

async function loadSingleStructure(
  plugin: PluginUIContext,
  options: {
    url: string
    format: StructureFormat
    isBinary?: boolean
  }
) {
  const { url, format, isBinary = !["pdb", "gro", "psf", "prmtop", "top"].includes(format) } = options

  const data = await plugin.builders.data.download({ url, isBinary }, { state: { isGhost: true } })

  if (!data || !data.isOk) {
    throw new Error(`Failed to download structure from ${url}`)
  }

  const provider = plugin.dataFormats.get(format)
  if (!provider) {
    throw new Error(`Unsupported structure format: ${format}`)
  }

  const parsed = await provider.parse(plugin, data)
  // Trajectory formats yield { trajectory }; topology formats yield { topology }
  if ("trajectory" in parsed) {
    await plugin.builders.structure.hierarchy.applyPreset(parsed.trajectory, "default")
  } else {
    await plugin.builders.structure.hierarchy.applyPreset(parsed.topology, "default")
  }
}

/**
 * Load a structure/topology + coordinates pair as a trajectory.
 * Mirrors MolStar's own LoadTrajectory action:
 * - Parses structure via dataFormats registry (handles both trajectory and topology formats)
 * - Parses coordinates via dataFormats registry (handles all coordinate formats)
 * - Combines them with TrajectoryFromModelAndCoordinates
 */
async function loadStructureWithCoordinates(
  plugin: PluginUIContext,
  options: {
    structureUrl: string
    structureFormat: StructureFormat
    coordsUrl: string
    coordsFormat: CoordsFormat
  }
) {
  const { structureUrl, structureFormat, coordsUrl, coordsFormat } = options
  const state = plugin.state.data

  // Download and parse structure/topology
  const structureIsBinary = !["pdb", "gro", "psf", "prmtop", "top"].includes(structureFormat)
  const structureData = await plugin.builders.data.download(
    { url: structureUrl, isBinary: structureIsBinary },
    { state: { isGhost: true } }
  )

  if (!structureData || !structureData.isOk) {
    throw new Error(`Failed to download structure file from ${structureUrl}`)
  }

  const structureProvider = plugin.dataFormats.get(structureFormat)
  if (!structureProvider) {
    throw new Error(`Unsupported structure format: ${structureFormat}`)
  }

  const structureParsed = await structureProvider.parse(plugin, structureData)

  // Trajectory formats (pdb, gro) yield { trajectory } → create a model from it
  // Topology formats (prmtop, psf, top) yield { topology } → use directly
  const model = "trajectory" in structureParsed
    ? (await plugin.builders.structure.createModel(structureParsed.trajectory))
    : structureParsed.topology

  if (!model || !model.isOk) {
    throw new Error(`Failed to create model from ${structureFormat}`)
  }

  // Download and parse coordinates via dataFormats registry
  const coordsProvider = plugin.dataFormats.get(coordsFormat)
  if (!coordsProvider) {
    throw new Error(`Unsupported coordinates format: ${coordsFormat}`)
  }

  const coordsData = await plugin.builders.data.download(
    { url: coordsUrl, isBinary: true },
    { state: { isGhost: true } }
  )

  if (!coordsData || !coordsData.isOk) {
    throw new Error(`Failed to download coordinates file from ${coordsUrl}`)
  }

  const coords = await coordsProvider.parse(plugin, coordsData)

  if (!coords || !coords.isOk) {
    throw new Error(`Failed to parse coordinates file as ${coordsFormat}`)
  }

  // Combine structure/topology model with coordinates
  try {
    const trajectory = await state
      .build()
      .toRoot()
      .apply(
        StateTransforms.Model.TrajectoryFromModelAndCoordinates,
        {
          modelRef: model.ref,
          coordinatesRef: coords.ref,
        },
        { dependsOn: [model.ref, coords.ref] }
      )
      .commit({ revertOnError: true })

    if (!trajectory || !trajectory.isOk) {
      throw new Error("Failed to create trajectory from structure and coordinates")
    }

    await plugin.builders.structure.hierarchy.applyPreset(trajectory, "default")
  } catch (e) {
    throw new Error(`Failed to create trajectory from structure and coordinates: ${e instanceof Error ? e.message : String(e)}`)
  }
}

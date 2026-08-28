import type { BuiltInCoordinatesFormat } from "molstar/lib/mol-plugin-state/formats/coordinates"
import type { BuiltInTopologyFormat } from "molstar/lib/mol-plugin-state/formats/topology"
import type { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory"

export type StructureFormat = BuiltInTrajectoryFormat | BuiltInTopologyFormat
export type CoordsFormat = BuiltInCoordinatesFormat

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

const COORDS_FORMAT_MAP: Record<string, CoordsFormat> = {
  xtc: "xtc",
  trr: "trr",
  dcd: "dcd",
  nc: "nctraj",
  nctraj: "nctraj",
  lammpstrj: "lammpstrj",
}

export function resolveStructureFormat(filename: string): StructureFormat {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  return STRUCTURE_FORMAT_MAP[ext] ?? "pdb"
}

export function resolveCoordsFormat(filename: string): CoordsFormat {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  return COORDS_FORMAT_MAP[ext] ?? "xtc"
}

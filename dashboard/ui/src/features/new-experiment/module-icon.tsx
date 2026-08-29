import type { NotebookModuleCategory } from "@/api/generated/models"
import { Atom, Dna, Hexagon, Layers, Link2, SlidersHorizontal, Spline, Wheat, type LucideIcon } from "lucide-react"

/** Exhaustive by type: adding a catalog category without an icon breaks the build. */
const CATEGORY_ICONS: Record<NotebookModuleCategory, LucideIcon> = {
  protein: Atom,
  "membrane-protein": Layers,
  "nucleic-acids": Dna,
  "protein-ligand": Link2,
  "small-molecule": Hexagon,
  carbohydrate: Wheat,
  polymer: Spline,
}

/** Decorative icon for a catalog workflow — callers hide its tile from assistive tech. */
export function ModuleIcon({ category, size = 20 }: { category: NotebookModuleCategory; size?: number }) {
  const Icon = CATEGORY_ICONS[category]
  return <Icon size={size} aria-hidden="true" />
}

/** Decorative icon representing the bring-your-own-repository workflow. */
export function CustomWorkflowIcon({ size = 20 }: { size?: number }) {
  return <SlidersHorizontal size={size} aria-hidden="true" />
}

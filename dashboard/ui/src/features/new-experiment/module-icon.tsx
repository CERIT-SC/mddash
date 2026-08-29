import type { NotebookModuleCategory } from "@/api/generated/models"
import { cn } from "@e-infra/design-system"
import { Atom, Dna, Hexagon, Layers, Link2, SlidersHorizontal, Spline, Wheat, type LucideIcon } from "lucide-react"

/**
 * Category presentation: glyph + filled semantic tile, mirroring the experiment
 * card's step tiles. Exhaustive by type — a new catalog category without an entry
 * here breaks the build. Tile color is keyed to the category; the engine stays
 * text in the subtitle, same as module/engine does on experiment cards.
 */
const CATEGORY_PRESENTATION: Record<NotebookModuleCategory, { Icon: LucideIcon; tileClass: string }> = {
  protein: { Icon: Atom, tileClass: "bg-primary text-primary-foreground" },
  "membrane-protein": { Icon: Layers, tileClass: "bg-warning text-warning-foreground" },
  "nucleic-acids": { Icon: Dna, tileClass: "bg-success text-success-foreground" },
  "protein-ligand": { Icon: Link2, tileClass: "bg-tertiary text-tertiary-foreground" },
  "small-molecule": { Icon: Hexagon, tileClass: "bg-info text-info-foreground" },
  carbohydrate: { Icon: Wheat, tileClass: "bg-secondary text-secondary-foreground" },
  polymer: { Icon: Spline, tileClass: "bg-error text-error-foreground" },
}

/** Filled icon tile used on workflow cards — same h-11 rounded-lg size as experiment cards. */
export function ModuleIconTile({ category }: { category: NotebookModuleCategory }) {
  const { Icon, tileClass } = CATEGORY_PRESENTATION[category]
  return (
    <span
      className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-lg", tileClass)}
      aria-hidden="true"
    >
      <Icon size={20} aria-hidden="true" />
    </span>
  )
}

/** Bare decorative icon for neutral contexts (creation dialog header). */
export function ModuleIcon({ category, size = 20 }: { category: NotebookModuleCategory; size?: number }) {
  const { Icon } = CATEGORY_PRESENTATION[category]
  return <Icon size={size} aria-hidden="true" />
}

/** Decorative icon representing the bring-your-own-repository workflow. */
export function CustomWorkflowIcon({ size = 20 }: { size?: number }) {
  return <SlidersHorizontal size={size} aria-hidden="true" />
}

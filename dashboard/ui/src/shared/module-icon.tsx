import type { NotebookModuleCategory } from "@/api/generated/models"
import { cn } from "@e-infra/design-system"
import { Atom, Dna, GitFork, Hexagon, Layers, Link2, Spline, Wheat, type LucideIcon } from "lucide-react"

const CATEGORY_PRESENTATION: Record<NotebookModuleCategory, { Icon: LucideIcon; tileClass: string }> = {
  protein: { Icon: Atom, tileClass: "bg-primary text-primary-foreground" },
  "membrane-protein": { Icon: Layers, tileClass: "bg-warning text-warning-foreground" },
  "nucleic-acids": { Icon: Dna, tileClass: "bg-success text-success-foreground" },
  "protein-ligand": { Icon: Link2, tileClass: "bg-tertiary text-tertiary-foreground" },
  "small-molecule": { Icon: Hexagon, tileClass: "bg-info text-info-foreground" },
  carbohydrate: { Icon: Wheat, tileClass: "bg-secondary text-secondary-foreground" },
  polymer: { Icon: Spline, tileClass: "bg-error text-error-foreground" },
}

/** The user's own git repository of notebooks, as opposed to a curated workflow. */
const CUSTOM_PRESENTATION: { Icon: LucideIcon; tileClass: string } = {
  Icon: GitFork,
  tileClass: "bg-surface-raised text-text-muted",
}

// The category set evolves independently of deployed UIs (new catalog entries,
// old experiments' snapshots) — unknown values must fall back, never crash.
const presentation = (category?: NotebookModuleCategory | null) =>
  (category && CATEGORY_PRESENTATION[category]) || CUSTOM_PRESENTATION

/** Category tile; null (custom workflow) or an unknown category renders the custom fallback. */
export function ModuleIconTile({ category }: { category?: NotebookModuleCategory | null }) {
  const { Icon, tileClass } = presentation(category)
  return (
    <span
      className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-lg", tileClass)}
      aria-hidden="true"
    >
      <Icon size={20} aria-hidden="true" />
    </span>
  )
}

/** Bare icon for neutral contexts (creation dialog header). */
export function ModuleIcon({ category, size = 20 }: { category: NotebookModuleCategory; size?: number }) {
  const { Icon } = presentation(category)
  return <Icon size={size} aria-hidden="true" />
}

/** The user's own git repository of notebooks, as opposed to a curated workflow. */
export function CustomWorkflowIcon({ size = 20 }: { size?: number }) {
  return <GitFork size={size} aria-hidden="true" />
}

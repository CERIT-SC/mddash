import type { NotebookModuleIcon } from "@/api/generated/models"
import { Atom, Layers, SlidersHorizontal, type LucideIcon } from "lucide-react"

/** Symbolic catalog icon keys mapped to the app's icon set. */
const MODULE_ICONS: Record<NotebookModuleIcon, LucideIcon> = {
  protein: Atom,
  membrane: Layers,
}

/** Decorative icon for a catalog workflow — callers hide its tile from assistive tech. */
export function ModuleIcon({ icon, size = 20 }: { icon: NotebookModuleIcon; size?: number }) {
  const Icon = MODULE_ICONS[icon]
  return <Icon size={size} aria-hidden="true" />
}

/** Decorative icon representing the bring-your-own-repository workflow. */
export function CustomWorkflowIcon({ size = 20 }: { size?: number }) {
  return <SlidersHorizontal size={size} aria-hidden="true" />
}

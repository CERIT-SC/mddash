import type { NotebookModule } from "@/api/generated/models"
import { ENGINE_LABELS } from "@/shared/engine"
import { CATEGORY_LABELS } from "@/shared/notebook-module"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@e-infra/design-system"

import { ModuleIcon } from "./module-icon"

type WorkflowCardProps = {
  module: NotebookModule
  onSelect: () => void
}

/**
 * A single curated workflow. The whole card activates via a stretched button on the
 * title (same overlay pattern as experiment cards): DS cards are borderless
 * (shadow-only), so hover means lift, and focus lands on the title button.
 * Names wrap to a second line instead of truncating — they are the card's primary
 * identifier, and the curated set is short enough to always show in full.
 */
export function WorkflowCard({ module, onSelect }: WorkflowCardProps) {
  return (
    <Card className="relative transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex min-w-0 items-center gap-3">
          <span
            className="bg-surface text-text-muted flex h-11 w-11 shrink-0 items-center justify-center rounded-lg"
            aria-hidden="true"
          >
            <ModuleIcon category={module.category} />
          </span>
          <div className="min-w-0">
            <CardTitle className="leading-tight">
              {/* Names repeat across engines ("Protein" ×2) — the engine disambiguates. */}
              <button
                type="button"
                onClick={onSelect}
                aria-label={`${module.name} · ${ENGINE_LABELS[module.engine]}`}
                className="focus-visible:ring-border-focus/50 rounded-sm text-left after:absolute after:inset-0 focus-visible:ring-[3px] focus-visible:outline-none"
              >
                {module.name}
              </button>
            </CardTitle>
            <p className="text-text-muted truncate text-sm">
              {CATEGORY_LABELS[module.category]} · {ENGINE_LABELS[module.engine]}
            </p>
          </div>
        </div>
      </CardHeader>
      {module.description && (
        <CardContent>
          <p className="text-text-muted line-clamp-2 text-sm">{module.description}</p>
        </CardContent>
      )}
      <CardFooter>
        <span className="text-text-muted text-xs">{module.author}</span>
      </CardFooter>
    </Card>
  )
}

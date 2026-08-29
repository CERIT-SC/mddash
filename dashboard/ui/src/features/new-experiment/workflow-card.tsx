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
 * Hover tooltips are per zone: the truncated name span shows the full name, and the
 * truncated description rises above the overlay (z-10) with its own full text.
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
              {/* The inner span truncates (block box → a real ellipsis) and owns the
                  full-name tooltip. The button must NOT carry overflow-hidden: a clipped
                  ancestor between it and the Card would shrink its ::after overlay back
                  to the title box; nor a title, which would fire over the whole card. */}
              <button
                type="button"
                onClick={onSelect}
                aria-label={`${module.name} · ${ENGINE_LABELS[module.engine]}`}
                className="focus-visible:ring-border-focus/50 block w-full rounded-sm text-left after:absolute after:inset-0 focus-visible:ring-[3px] focus-visible:outline-none"
              >
                <span className="block truncate" title={module.name}>
                  {module.name}
                </span>
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
          {/* z-10 rises above the card's stretched-overlay button so the description's
              own full-text tooltip can fire; this strip is hover-only, not a click target. */}
          <p className="text-text-muted relative z-10 line-clamp-2" title={module.description}>
            {module.description}
          </p>
        </CardContent>
      )}
      <CardFooter>
        <span className="text-text-muted text-sm">{module.author}</span>
      </CardFooter>
    </Card>
  )
}

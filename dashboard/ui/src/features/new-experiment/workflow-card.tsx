import type { NotebookModule } from "@/api/generated/models"
import { ENGINE_LABELS } from "@/shared/engine"
import { CATEGORY_LABELS } from "@/shared/notebook-module"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@e-infra/design-system"

import { ModuleIconTile } from "./module-icon"

type WorkflowCardProps = {
  module: NotebookModule
  onSelect: () => void
}

/**
 * A single curated workflow. Deliberately a separate component from the experiment
 * card (static catalog selection vs. live-state monitor), but sharing its visual
 * shell: same tile sizing, title/subtitle typography, colored category tile, and
 * raised footer band. The whole card activates via a stretched button on the title
 * (same overlay pattern as experiment cards): DS cards are borderless (shadow-only),
 * so hover means lift, and focus lands on the title button. Hover tooltips are per
 * zone: the truncated name span shows the full name, and the truncated description
 * rises above the overlay (z-10) with its own full text.
 */
export function WorkflowCard({ module, onSelect }: WorkflowCardProps) {
  return (
    <Card className="relative pb-0 transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex min-w-0 items-center gap-3">
          <ModuleIconTile category={module.category} />
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
      {/* Same footer band as experiment cards: surface-raised is the only legal surface
          step above bg-surface; pt-3! outranks the DS rule padding border-t footers to pt-6. */}
      <CardFooter className="border-border bg-surface-raised gap-3 rounded-b-md border-t pt-3! pb-3 text-sm">
        <span className="text-text-muted truncate">{module.author}</span>
      </CardFooter>
    </Card>
  )
}

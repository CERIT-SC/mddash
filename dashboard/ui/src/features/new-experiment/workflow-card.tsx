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
 * Catalog selection card: shares the experiment card's visual shell, not its
 * component (static selection vs. live-state monitor; different lifecycles).
 */
export function WorkflowCard({ module, onSelect }: WorkflowCardProps) {
  return (
    <Card className="relative pb-0 transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex min-w-0 items-center gap-3">
          <ModuleIconTile category={module.category} />
          <div className="min-w-0">
            <CardTitle className="leading-tight">
              {/* aria-label adds the engine: names repeat across engines ("Protein" ×2). */}
              {/* The span truncates and owns the tooltip; the button stays overflow-free
                  (clipping would shrink its ::after overlay to the title row) and title-free. */}
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
          {/* z-10 lifts above the card overlay so its tooltip fires; hover-only strip. */}
          <p className="text-text-muted relative z-10 line-clamp-2" title={module.description}>
            {module.description}
          </p>
        </CardContent>
      )}
      {/* Experiment-card footer band: surface-raised is the only legal step above
          bg-surface; pt-3! outranks the DS border-t pt-6 rule. */}
      <CardFooter className="border-border bg-surface-raised gap-3 rounded-b-md border-t pt-3! pb-3 text-sm">
        <span className="text-text-muted truncate">{module.author}</span>
      </CardFooter>
    </Card>
  )
}

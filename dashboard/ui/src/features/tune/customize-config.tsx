import { Engine } from "@/api/generated/models"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@e-infra/design-system"
import { ChevronDown } from "lucide-react"

import { HardwareConfigForm } from "./hardware-config-form"
import type { HardwareConfigValues } from "./hardware-config-form"
import type { TrialRow } from "./tuned-trials"

type CustomizeConfigSectionProps = {
  engine: Engine
  /** The picked trial — pre-fills the form. */
  row: TrialRow
  /** Lets the footer Run button submit this form via the native form attribute. */
  formId: string
  onSubmit: (values: HardwareConfigValues) => void
  onValidityChange: (valid: boolean) => void
}

// forceMount keeps edits across collapse/expand; `key` re-seeds on pick change.
export function CustomizeConfigSection({
  engine,
  row,
  formId,
  onSubmit,
  onValidityChange,
}: CustomizeConfigSectionProps) {
  const gmx = engine !== Engine.AMBER
  const initial = {
    pickA: (gmx ? row.pme : row.binary) ?? "",
    pickB: (gmx ? row.nb : row.ewald) ?? "",
    np: row.np ?? "",
    ntomp: row.ntomp ?? "",
  }

  return (
    <Collapsible>
      <CollapsibleTrigger className="text-text-muted hover:text-text group inline-flex items-center gap-1 text-xs font-semibold tracking-wide uppercase">
        Customize selected configuration
        <ChevronDown className="h-3.5 w-3.5 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
      </CollapsibleTrigger>
      <CollapsibleContent forceMount className="pt-5 data-[state=closed]:hidden">
        <HardwareConfigForm
          key={row.id}
          engine={engine}
          initial={initial}
          formId={formId}
          onSubmit={onSubmit}
          onValidityChange={onValidityChange}
        />
      </CollapsibleContent>
    </Collapsible>
  )
}

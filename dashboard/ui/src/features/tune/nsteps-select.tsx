import { useState } from "react"

import { Button, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"
import { PenLine, Undo2 } from "lucide-react"

export const DEFAULT_NSTEPS = 25_000

const PRESETS = [
  { value: 10_000, hint: "quick, less precise" },
  { value: DEFAULT_NSTEPS, hint: "recommended" },
  { value: 50_000, hint: "for large systems" },
] as const

// Radix items can't be empty strings; this sentinel swaps in the free-form input.
const CUSTOM = "custom"

type NstepsSelectProps = {
  value: number
  onValueChange: (nsteps: number) => void
  disabled?: boolean
  id?: string
}

// Off-preset values (e.g. an existing job's custom nsteps) render as the input directly.
export function NstepsSelect({ value, onValueChange, disabled = false, id }: NstepsSelectProps) {
  const isPreset = PRESETS.some((preset) => preset.value === value)
  const [custom, setCustom] = useState(!isPreset)
  const [text, setText] = useState(String(value))

  if (custom) {
    const commit = (raw: string) => {
      setText(raw)
      const parsed = Number.parseInt(raw, 10)
      if (Number.isInteger(parsed) && parsed >= 1) onValueChange(parsed)
    }
    return (
      <div className="flex w-full max-w-72 items-center gap-1">
        <Input
          id={id}
          type="number"
          min={1}
          value={text}
          disabled={disabled}
          autoFocus={!disabled}
          placeholder="Number of steps"
          aria-label="Custom number of steps"
          onChange={(event) => commit(event.target.value)}
          onBlur={() => setText(String(value))}
        />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Back to presets"
          disabled={disabled}
          onClick={() => {
            setCustom(false)
            if (!PRESETS.some((preset) => preset.value === value)) onValueChange(DEFAULT_NSTEPS)
          }}
        >
          <Undo2 />
        </Button>
      </div>
    )
  }

  return (
    <Select
      value={String(value)}
      disabled={disabled}
      onValueChange={(next) => {
        if (next === CUSTOM) {
          setText(String(value))
          setCustom(true)
        } else {
          onValueChange(Number(next))
        }
      }}
    >
      <SelectTrigger id={id} className="w-full max-w-72 [&_[data-hint]]:hidden">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PRESETS.map((preset) => (
          <SelectItem key={preset.value} value={String(preset.value)} textValue={formatSteps(preset.value)}>
            {formatSteps(preset.value)}
            {/* Radix renders the whole ItemText in the trigger; data-hint hides it there. */}
            <span data-hint className="text-text-muted ml-2">
              — {preset.hint}
            </span>
          </SelectItem>
        ))}
        <SelectItem value={CUSTOM} textValue="Enter custom value…" className="text-primary">
          <PenLine className="text-primary h-3.5 w-3.5" />
          Enter custom value…
        </SelectItem>
      </SelectContent>
    </Select>
  )
}

function formatSteps(steps: number): string {
  return steps.toLocaleString("en-US")
}

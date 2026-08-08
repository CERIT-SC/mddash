import { useState } from "react"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export const DEFAULT_NSTEPS = 25000

const CUSTOM_OPTION = "custom"

const PRESETS = [
  { nsteps: 10000, label: "10,000 — faster, less accurate" },
  { nsteps: 25000, label: "25,000 — balanced (default)" },
  { nsteps: 50000, label: "50,000 — slower, most accurate" },
]

interface NstepsPickerProps {
  value: number | ""
  onChange: (value: number | "") => void
}

const NstepsPicker = ({ value, onChange }: NstepsPickerProps) => {
  const [selected, setSelected] = useState<string>(String(DEFAULT_NSTEPS))

  const handleSelect = (option: string) => {
    setSelected(option)
    if (option !== CUSTOM_OPTION) onChange(Number(option))
  }

  return (
    <div className="flex w-72 flex-col gap-1">
      <Label htmlFor="nsteps-select">Number of steps (nsteps)</Label>
      <Select value={selected} onValueChange={handleSelect}>
        <SelectTrigger id="nsteps-select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PRESETS.map((preset) => (
            <SelectItem key={preset.nsteps} value={String(preset.nsteps)}>
              {preset.label}
            </SelectItem>
          ))}
          <SelectItem value={CUSTOM_OPTION}>Custom…</SelectItem>
        </SelectContent>
      </Select>
      {selected === CUSTOM_OPTION && (
        <Input
          type="number"
          min={1}
          placeholder="Custom number of steps"
          value={value}
          onChange={(e) => {
            const val = e.target.value
            onChange(val === "" ? "" : parseInt(val) || "")
          }}
        />
      )}
    </div>
  )
}

export default NstepsPicker

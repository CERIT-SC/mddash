import { Engine, JobStatus } from "@/api/generated/models"
import { formatTime } from "@/shared/format"
import { HintTooltip } from "@/shared/ui/hint-tooltip"
import {
  Badge,
  Button,
  RadioGroup,
  RadioGroupItem,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@e-infra/design-system"
import { FileText, Leaf, LoaderCircle, Zap } from "lucide-react"

import { formatCost, formatHardware, selectable, sortTrials, suggest, type TrialRow } from "./tuned-trials"

const COLUMN_COUNT = 9

const GMX_HARDWARE: [string, string][] = [
  ["PME", "Where long-range electrostatics (Particle Mesh Ewald) are computed."],
  ["NB", "Where short-range non-bonded interactions are computed."],
]

const AMBER_HARDWARE: [string, string][] = [
  ["Binary", "AMBER executable variant the trial ran with."],
  ["Ewald", "Ewald summation preset applied to the simulation settings."],
]

type TrialsTableProps = {
  engine: Engine
  rows: TrialRow[]
  value: string | undefined
  onValueChange: (trialId: string) => void
  /** Whether the tuner is still producing results (drives the waiting row). */
  live: boolean
  onShowLogs: (trialId: string) => void
}

/**
 * Header shared by the trials picker and the Run step's single-row
 * "configuration used" table (pickColumn hides the radio column there).
 */
export function TrialsTableHeader({ engine, pickColumn = true }: { engine: Engine; pickColumn?: boolean }) {
  return (
    <TableHeader>
      {/* Primary band matches the pre-rewrite TunerTable header; hover stays
          primary so the DS row hover doesn't wash it out. */}
      <TableRow className="bg-primary hover:bg-primary">
        {pickColumn && (
          <TableHead className="text-primary-foreground w-10">
            <span className="sr-only">Pick</span>
          </TableHead>
        )}
        <TableHead className="text-primary-foreground text-center">Status</TableHead>
        <HintedHead
          label="Performance"
          hint="Throughput measured during the tuning run (ns of simulated time per day). Higher is faster."
        />
        <HintedHead
          label="Est. time"
          hint="Estimated wall-clock time for the full production simulation with this configuration."
        />
        <HintedHead
          label="Est. cost"
          hint="Estimated compute cost for the full production simulation with this configuration."
        />
        {/* Hardware config grouped apart from the outcome columns by a divider. */}
        {(engine === Engine.AMBER ? AMBER_HARDWARE : GMX_HARDWARE).map(([label, hint], index) => (
          <HintedHead key={label} label={label} hint={hint} separated={index === 0} />
        ))}
        <HintedHead label="MPI processes" hint="Number of parallel MPI ranks." />
        <HintedHead label="Threads" hint="CPU threads per MPI rank." />
      </TableRow>
    </TableHeader>
  )
}

/** Suggestions (fastest/cheapest) in a band up top; the rest sorted by performance below. */
export function TrialsTable({ engine, rows, value, onValueChange, live, onShowLogs }: TrialsTableProps) {
  const { fastestId, ecoId } = suggest(rows)
  // Fastest and eco may be the same row — dedupe before mapping.
  const sorted = sortTrials(rows)
  const suggested = [...new Set([fastestId, ecoId])]
    .map((id) => sorted.find((row) => row.id === id))
    .filter((row): row is TrialRow => row !== undefined)
  const others = sorted.filter((row) => row.id !== fastestId && row.id !== ecoId)

  return (
    <RadioGroup value={value ?? ""} onValueChange={onValueChange} aria-label="Pick a configuration">
      <div className="overflow-x-auto">
        <Table>
          <TrialsTableHeader engine={engine} />
          <TableBody>
            {rows.length === 0 && live && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={COLUMN_COUNT}>
                  <span className="text-text-muted flex items-center gap-2 text-sm">
                    <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
                    Waiting for the first trials…
                  </span>
                </TableCell>
              </TableRow>
            )}
            {suggested.length > 0 && (
              <>
                <GroupBand label="Suggested" />
                {suggested.map((row) => (
                  <TrialRowView
                    key={row.id}
                    engine={engine}
                    row={row}
                    fastest={row.id === fastestId}
                    eco={row.id === ecoId}
                    onShowLogs={onShowLogs}
                  />
                ))}
              </>
            )}
            {suggested.length > 0 && others.length > 0 && <GroupBand label="Other configurations" />}
            {others.map((row) => (
              <TrialRowView
                key={row.id}
                engine={engine}
                row={row}
                fastest={false}
                eco={false}
                onShowLogs={onShowLogs}
              />
            ))}
          </TableBody>
        </Table>
      </div>
    </RadioGroup>
  )
}

/** aria-label keeps the hint button's text out of the columnheader's accessible name. */
function HintedHead({ label, hint, separated = false }: { label: string; hint: string; separated?: boolean }) {
  return (
    <TableHead
      aria-label={label}
      className={
        separated ? "text-primary-foreground border-primary-foreground/30 border-l pl-6" : "text-primary-foreground"
      }
    >
      <span className="inline-flex items-center gap-1 whitespace-nowrap">
        {label}
        {/* Muted gray would die on the primary band; inherit its foreground. */}
        <span className="[&_button]:text-primary-foreground/60 [&_button:hover]:text-primary-foreground contents">
          <HintTooltip text={hint} />
        </span>
      </span>
    </TableHead>
  )
}

function GroupBand({ label }: { label: string }) {
  return (
    <TableRow className="bg-surface hover:bg-surface">
      {/* Two cells so the hardware divider runs unbroken through the band. */}
      <TableCell
        colSpan={COLUMN_COUNT - 4}
        className="text-text-muted py-2 text-xs font-semibold tracking-wide uppercase"
      >
        {label}
      </TableCell>
      <TableCell colSpan={4} className="border-border border-l" />
    </TableRow>
  )
}

type TrialRowCellsProps = {
  engine: Engine
  row: TrialRow
  fastest: boolean
  eco: boolean
  /** Error-row log button; omit where trial logs are not reachable (e.g. the Run step). */
  onShowLogs?: (trialId: string) => void
}

/** The trial's cells (no surrounding TableRow) — shared by the picker and "configuration used". */
export function TrialRowCells({ engine, row, fastest, eco, onShowLogs }: TrialRowCellsProps) {
  return (
    <>
      <TableCell className="text-center">
        <TrialStatus row={row} fastest={fastest} eco={eco} onShowLogs={onShowLogs} />
      </TableCell>
      <TableCell className="tabular-nums">{row.performance === null ? "—" : row.performance.toFixed(2)}</TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">
        {row.estTimeHours === null ? "—" : formatTime(row.estTimeHours * 3600)}
      </TableCell>
      <TableCell className="tabular-nums">{row.estCost === null ? "—" : formatCost(row.estCost)}</TableCell>
      {/* Hardware cells are confirmation detail — muted so badges and outcomes win the eye. */}
      {engine === Engine.AMBER ? (
        <>
          <TableCell className="text-text-muted border-border border-l pl-6 whitespace-nowrap">
            {row.binary ?? "—"}
          </TableCell>
          <TableCell className="text-text-muted">{row.ewald ?? "—"}</TableCell>
        </>
      ) : (
        <>
          <TableCell className="text-text-muted border-border border-l pl-6">{formatHardware(row.pme)}</TableCell>
          <TableCell className="text-text-muted">{formatHardware(row.nb)}</TableCell>
        </>
      )}
      <TableCell className="text-text-muted tabular-nums">{row.np ?? "—"}</TableCell>
      <TableCell className="text-text-muted tabular-nums">{row.ntomp ?? "—"}</TableCell>
    </>
  )
}

type TrialRowViewProps = Omit<TrialRowCellsProps, "onShowLogs"> & {
  onShowLogs: (trialId: string) => void
}

function TrialRowView({ engine, row, fastest, eco, onShowLogs }: TrialRowViewProps) {
  return (
    <TableRow>
      <TableCell>
        <RadioGroupItem value={row.id} disabled={!selectable(row)} aria-label={`Pick configuration ${row.id}`} />
      </TableCell>
      <TrialRowCells engine={engine} row={row} fastest={fastest} eco={eco} onShowLogs={onShowLogs} />
    </TableRow>
  )
}

function TrialStatus({ row, fastest, eco, onShowLogs }: Omit<TrialRowCellsProps, "engine">) {
  if (fastest || eco) {
    return (
      <span className="flex flex-wrap items-center justify-center gap-1.5">
        {fastest && (
          <Badge className="gap-1 [&>svg]:size-3">
            <Zap aria-hidden />
            Fastest
          </Badge>
        )}
        {eco && (
          <Badge className="bg-success text-success-foreground gap-1 border-transparent [&>svg]:size-3">
            <Leaf aria-hidden />
            Eco
          </Badge>
        )}
      </span>
    )
  }
  if (row.status === JobStatus.PENDING) {
    return <span className="text-text-muted text-sm">Queued…</span>
  }
  if (row.status === JobStatus.RUNNING) {
    return <LoaderCircle className="text-text-muted mx-auto h-4 w-4 animate-spin" role="img" aria-label="Running" />
  }
  if (row.status === JobStatus.ERROR) {
    return (
      <span className="flex items-center justify-center gap-1">
        <Badge variant="error">Failed</Badge>
        {onShowLogs !== undefined && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`View output of failed trial ${row.id}`}
            onClick={() => onShowLogs(row.id)}
          >
            <FileText aria-hidden />
          </Button>
        )}
      </span>
    )
  }
  return null
}

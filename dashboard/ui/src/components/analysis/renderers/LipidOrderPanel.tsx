import { useEffect, useMemo, useState, type FC } from "react"

import type { LipidOrderAnalysis } from "@/util/analysis-types"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { LineChart } from "@/components/charts"
import type { LineSeries } from "@/components/charts/LineChart"

const sanitizeNumericArray = (values: unknown): number[] => {
  if (!Array.isArray(values)) return []
  return values
    .map((value) => (typeof value === "number" && Number.isFinite(value) ? value : null))
    .filter((value): value is number => value !== null)
}

const sanitizeStringArray = (values: unknown): string[] => {
  if (!Array.isArray(values)) return []
  return values
    .map((value) => (typeof value === "string" ? value : null))
    .filter((value): value is string => Boolean(value))
}

const buildSeries = (label: string, xValues: number[], yValues: number[]): LineSeries | undefined => {
  if (!xValues.length || !yValues.length) return undefined
  const limit = Math.min(xValues.length, yValues.length)
  const data: Array<[number, number]> = []
  for (let i = 0; i < limit; i += 1) {
    const x = xValues[i]
    const y = yValues[i]
    if (Number.isFinite(x) && Number.isFinite(y)) {
      data.push([x, y])
    }
  }
  return data.length ? { name: label, data } : undefined
}

type LipidSegment = {
  id: string
  label: string
  atoms: string[]
  avg: number[]
  std: number[]
}

type LipidEntry = {
  id: string
  label: string
  segments: LipidSegment[]
}

const LipidOrderPanel: FC<{ data: LipidOrderAnalysis }> = ({ data }) => {
  const lipids = useMemo<LipidEntry[]>(() => {
    if (!data?.data || typeof data.data !== "object") return []
    return Object.entries(data.data).map(([lipidName, rawSegments], lipidIndex) => {
      const segments = Object.entries(rawSegments ?? {}).map(([segmentName, segmentData], segmentIndex) => ({
        id: `${lipidName}-${segmentName || segmentIndex}`,
        label: segmentName && segmentName.trim().length ? segmentName.trim() : `Segment ${segmentIndex + 1}`,
        atoms: sanitizeStringArray(segmentData?.atoms),
        avg: sanitizeNumericArray(segmentData?.avg),
        std: sanitizeNumericArray(segmentData?.std),
      }))
      return {
        id: lipidName || `lipid-${lipidIndex}`,
        label: lipidName && lipidName.trim().length ? lipidName.trim() : `Lipid ${lipidIndex + 1}`,
        segments,
      }
    })
  }, [data])

  const [lipidId, setLipidId] = useState<string>(lipids[0]?.id ?? "")
  const [segmentId, setSegmentId] = useState<string>(lipids[0]?.segments[0]?.id ?? "")

  useEffect(() => {
    if (!lipids.length) return
    if (!lipids.some((lipid) => lipid.id === lipidId)) {
      setLipidId(lipids[0]?.id ?? "")
      setSegmentId(lipids[0]?.segments[0]?.id ?? "")
    }
  }, [lipids, lipidId])

  useEffect(() => {
    const selectedLipid = lipids.find((lipid) => lipid.id === lipidId)
    if (selectedLipid && !selectedLipid.segments.some((segment) => segment.id === segmentId)) {
      setSegmentId(selectedLipid.segments[0]?.id ?? "")
    }
  }, [lipidId, lipids, segmentId])

  const selectedLipid = lipids.find((lipid) => lipid.id === lipidId) ?? lipids[0]
  const selectedSegment = selectedLipid?.segments.find((segment) => segment.id === segmentId)

  const sampleCount = selectedSegment?.avg.length ?? 0
  const xPositions = useMemo(() => {
    if (!selectedSegment) return []
    return selectedSegment.avg.map((_, index) => index + 1)
  }, [selectedSegment])

  const lineSeries = useMemo(() => {
    if (!selectedSegment) return []
    const stdOverlay = selectedSegment.std.map((value) => (Number.isFinite(value) ? value : 0))
    const upper = selectedSegment.avg.map((value, index) => value + (stdOverlay[index] ?? 0))
    const lower = selectedSegment.avg.map((value, index) => value - (stdOverlay[index] ?? 0))
    const series = [
      buildSeries("Average S", xPositions, selectedSegment.avg),
      buildSeries("Average + std", xPositions, upper),
      buildSeries("Average - std", xPositions, lower),
    ].filter((entry): entry is LineSeries => Boolean(entry))
    return series
  }, [selectedSegment, xPositions])

  const averageOrder = useMemo(() => {
    if (!selectedSegment?.avg.length) return undefined
    const total = selectedSegment.avg.reduce((sum, value) => sum + value, 0)
    return total / selectedSegment.avg.length
  }, [selectedSegment])

  const maxOrder = useMemo(() => {
    if (!selectedSegment?.avg.length) return undefined
    return Math.max(...selectedSegment.avg)
  }, [selectedSegment])

  const avgStd = useMemo(() => {
    if (!selectedSegment?.std.length) return undefined
    const total = selectedSegment.std.reduce((sum, value) => sum + value, 0)
    return total / selectedSegment.std.length
  }, [selectedSegment])

  if (!lipids.length) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        No lipid order data available.
      </div>
    )
  }

  if (!selectedSegment || !lineSeries.length) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        The selected lipid does not contain usable segment data.
      </div>
    )
  }

  const formatStat = (value?: number) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : "N/A"

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-medium">Lipid order parameters</p>
          <p className="text-muted-foreground text-xs">
            Inspect segment order (S) per carbon and compare the standard deviation envelope.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={lipidId} onValueChange={setLipidId}>
            <SelectTrigger className="h-8 w-48 text-xs">
              <SelectValue placeholder="Lipid" />
            </SelectTrigger>
            <SelectContent>
              {lipids.map((lipid) => (
                <SelectItem key={lipid.id} value={lipid.id}>
                  {lipid.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedLipid?.segments.length ? (
            <Select value={segmentId} onValueChange={setSegmentId}>
              <SelectTrigger className="h-8 w-48 text-xs">
                <SelectValue placeholder="Segment" />
              </SelectTrigger>
              <SelectContent>
                {selectedLipid.segments.map((segment) => (
                  <SelectItem key={segment.id} value={segment.id}>
                    {segment.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Positions</p>
          <p className="text-lg font-semibold">{sampleCount}</p>
        </div>
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Avg S</p>
          <p className="text-lg font-semibold">{formatStat(averageOrder)}</p>
        </div>
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Max S</p>
          <p className="text-lg font-semibold">{formatStat(maxOrder)}</p>
        </div>
        <div className="border-border/70 rounded-md border p-3">
          <p className="text-muted-foreground/80 text-[11px] tracking-wide uppercase">Avg std</p>
          <p className="text-lg font-semibold">{formatStat(avgStd)}</p>
        </div>
      </div>

      <div className="border-border/60 flex min-h-[320px] flex-col rounded-lg border p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Segment order profile</p>
            <p className="text-muted-foreground text-xs">
              Average S with upper/lower bounds derived from the reported standard deviations.
            </p>
          </div>
          <Badge variant="outline" className="text-[11px]">
            {selectedSegment.label}
          </Badge>
        </div>
        <div className="min-h-[260px] flex-1">
          <LineChart series={lineSeries} xLabel="Position along chain" yLabel="S" showLegend yScale />
        </div>
      </div>

      <div className="border-border/60 rounded-lg border p-4">
        <p className="text-muted-foreground mb-3 text-xs tracking-wide uppercase">Atom labels</p>
        {selectedSegment.atoms.length ? (
          <div className="flex flex-wrap gap-2">
            {selectedSegment.atoms.map((atom, index) => (
              <Badge key={`${atom}-${index}`} variant="secondary">
                {index + 1}. {atom}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-xs">No atom names were provided for this segment.</p>
        )}
      </div>
    </div>
  )
}

export default LipidOrderPanel

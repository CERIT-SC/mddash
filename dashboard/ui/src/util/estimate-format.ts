// Human-readable formatting for tuner time/cost estimates.

export function formatEstimatedTime(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—"
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`
  if (hours < 48) return `${hours.toFixed(1)} h`
  return `${(hours / 24).toFixed(1)} d`
}

export function formatEstimatedCost(cost: number | null | undefined): string {
  if (cost === null || cost === undefined) return "—"
  if (cost < 0.01) return "<$0.01"
  return `$${cost.toFixed(2)}`
}

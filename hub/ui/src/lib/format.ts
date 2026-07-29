/** Format an ISO 8601 timestamp for display; returns "Never" when absent. */
export function formatTime(iso: string | null): string {
  if (!iso) return "Never"
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString()
}

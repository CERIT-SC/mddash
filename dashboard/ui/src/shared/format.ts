const UNITS = [
  { abbr: "d", secs: 86400 },
  { abbr: "h", secs: 3600 },
  { abbr: "m", secs: 60 },
  { abbr: "s", secs: 1 },
]

/**
 * Format a duration in seconds compactly with explicit units, using the two
 * most significant units (e.g. "9m", "2h 40m", "1d 3h", "47d"). Explicit
 * units stay unambiguous at every scale — unlike clock notation ("12:06"),
 * which collides with wall-clock readings and breaks past a day.
 */
export function formatTime(seconds: number): string {
  if (Number.isNaN(seconds)) return "?"
  let remaining = Math.max(0, Math.floor(seconds))
  const parts: string[] = []
  for (const { abbr, secs } of UNITS) {
    if (remaining >= secs) {
      const value = Math.floor(remaining / secs)
      parts.push(`${value}${abbr}`)
      remaining -= value * secs
    }
    if (parts.length === 2) break
  }
  return parts.length ? parts.join(" ") : "0s"
}

/**
 * Format a byte count as a compact human-readable size (e.g. "8.7 GB", "15 MB").
 */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`
  return `${Math.max(0, Math.round(bytes / 1024))} KB`
}

/**
 * Format an ISO timestamp as a short date (e.g. "Jul 20, 2026").
 */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

/**
 * Format an ISO timestamp as a human-friendly age (e.g. "12 min ago", "yesterday").
 */
export function relativeTime(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return "just now"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? "yesterday" : `${days} days ago`
}

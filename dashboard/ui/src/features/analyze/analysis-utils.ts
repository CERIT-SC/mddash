/**
 * Human-readable labels for analysis result names ("hbonds-00" → "Hydrogen
 * Bonds – 00").
 */

import { AVAILABLE_ANALYSES } from "./analysis-catalog"

// Human-friendly labels for base result identifiers (built from AVAILABLE_ANALYSES).
// Indexed by both value (e.g. "rmsf") and resultName (e.g. "fluctuation") so that
// result file names returned by the backend resolve to the correct label.
const BASE_LABELS: Record<string, string> = Object.fromEntries([
  ...AVAILABLE_ANALYSES.map((a) => [a.value, a.label]),
  ...AVAILABLE_ANALYSES.map((a) => [a.resultName, a.label]),
])

function toTitleCase(id: string): string {
  return id
    .replace(/[-_]+/g, " ")
    .split(" ")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ")
}

/** Returns a human-readable label for an analysis name or variant. */
export function getAnalysisLabel(name: string): string {
  const variantMatch = name.match(/^(.*?)-(\d+)$/)
  if (variantMatch) {
    const base = variantMatch[1]
    const idx = variantMatch[2]
    const baseLabel = BASE_LABELS[base] ?? toTitleCase(base)
    return `${baseLabel} – ${idx}`
  }
  return BASE_LABELS[name] ?? toTitleCase(name)
}

/**
 * Analysis grouping utilities — ported from invenio-app/src/components/layout/record/utils.ts.
 * Groups flat result name lists into base analyses with their numbered variants.
 */

import { AVAILABLE_ANALYSES } from "./analysis-types"

// Human-friendly labels for base result identifiers (built from AVAILABLE_ANALYSES)
const BASE_LABELS: Record<string, string> = Object.fromEntries(AVAILABLE_ANALYSES.map((a) => [a.value, a.label]))

function toTitleCase(id: string): string {
  return id
    .replace(/[-_]+/g, " ")
    .split(" ")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ")
}

/** Extracts the base identifier by removing a trailing -NN numeric suffix. */
export function getBaseAnalysisId(name: string): string {
  const m = name.match(/^(.*?)-(\d+)$/)
  return m ? m[1] : name
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

export type AnalysisGroup = {
  baseId: string
  label: string
  /** All selectable variant names (each maps to a numbered result file). */
  variants: string[]
  /** True when numbered variants (base-NN) were found in the available results. */
  hasVariants: boolean
}

/**
 * Groups a flat list of result names into base analyses with their variants.
 * e.g. ['rmsds', 'rmsd-pairwise-00', 'rmsd-pairwise-01', 'clusters-00'] →
 *   [ { baseId: 'rmsds', variants: ['rmsds'], hasVariants: false },
 *     { baseId: 'rmsd-pairwise', variants: ['rmsd-pairwise-00','rmsd-pairwise-01'], hasVariants: true },
 *     { baseId: 'clusters', variants: ['clusters-00'], hasVariants: true } ]
 */
export function groupAnalysesByBase(names: string[]): AnalysisGroup[] {
  type InternalGroup = AnalysisGroup & { baseSeen: boolean }

  const groups = new Map<string, InternalGroup>()
  const order: string[] = []

  for (const slug of names) {
    const baseId = getBaseAnalysisId(slug)
    let entry = groups.get(baseId)
    if (!entry) {
      entry = { baseId, label: getAnalysisLabel(baseId), variants: [], hasVariants: false, baseSeen: false }
      groups.set(baseId, entry)
      order.push(baseId)
    }
    if (slug === baseId) {
      entry.baseSeen = true
    } else {
      entry.hasVariants = true
      entry.variants.push(slug)
    }
  }

  return order.map((baseId) => {
    const entry = groups.get(baseId)!
    // If only the summary exists (no numbered variants), the summary is the sole selectable item
    if (entry.variants.length === 0) {
      entry.variants.push(entry.baseId)
    }
    return { baseId: entry.baseId, label: entry.label, variants: entry.variants, hasVariants: entry.hasVariants }
  })
}

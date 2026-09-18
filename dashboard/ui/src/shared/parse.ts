/**
 * Strictly parse a step-count-style input: digits only, positive, safe integer.
 *
 * `Number.parseInt` is not usable here; it silently prefixes ("1e5" → 1,
 * "5.9" → 5, "100abc" → 100), which for simulation step counts corrupts data
 * rather than merely refusing input.
 *
 * Returns the parsed integer, or null when the text is not a valid positive integer.
 */
export function parsePositiveInt(text: string): number | null {
  const trimmed = text.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const value = Number(trimmed)
  return Number.isSafeInteger(value) && value >= 1 ? value : null
}

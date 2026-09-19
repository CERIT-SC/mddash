/** Positive safe integer, else null (`parseInt` would prefix-match `"1e5"` to 1). */
export function parsePositiveInt(text: string): number | null {
  const trimmed = text.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const value = Number(trimmed)
  return Number.isSafeInteger(value) && value >= 1 ? value : null
}

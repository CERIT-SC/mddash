/**
 * The API job ladder (0–4; publish is experiment-level only, value 5) sits one
 * slot right of the [Setup, Tune, Run, Analyze, Publish] display index.
 */
export function ladderStepIndex(step: number): number {
  return Math.max(0, Math.min(step === 0 ? 0 : step - 1, 4))
}

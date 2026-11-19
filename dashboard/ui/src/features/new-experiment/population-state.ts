import type { PopulationOperationStatus } from "@/api/generated/models"

/** Non-terminal population states. The operation is polled while in either. */
export function populationActive(status: string | null | undefined): boolean {
  return status === "queued" || status === "running"
}

/** TanStack Query refetchInterval: poll only while the operation is still active. */
export function pollWhilePopulationActive(pollMs: number) {
  return (query: { state: { data: unknown } }): number | false => {
    const data = query.state.data as { status: number; data: PopulationOperationStatus } | undefined
    return data?.status === 200 && populationActive(data.data.status) ? pollMs : false
  }
}

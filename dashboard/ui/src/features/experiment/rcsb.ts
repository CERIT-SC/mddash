import { useQuery } from "@tanstack/react-query"

// Fields read from the RCSB PDB Data API; everything else in the responses is ignored.
const RCSB_API = "https://data.rcsb.org/rest/v1/core"

export type PdbEntry = {
  title: string | null
  experimentalMethod: string | null
  resolutionAngstrom: number | null
  releasedDate: string | null
  authors: string | null
  organism: string | null
}

export class PdbNotFoundError extends Error {}

async function fetchJson(url: string, signal?: AbortSignal): Promise<Response> {
  const response = await fetch(url, { signal })
  if (response.status === 404) throw new PdbNotFoundError(url)
  if (!response.ok) throw new Error(`RCSB PDB request failed: ${String(response.status)}`)
  return response
}

/**
 * Display data for a PDB entry; the polymer-entity call is best-effort —
 * synthetic constructs leave organism null.
 */
export async function fetchPdbEntry(pdbId: string, signal?: AbortSignal): Promise<PdbEntry> {
  const id = encodeURIComponent(pdbId)
  const [entry, entity] = await Promise.allSettled([
    fetchJson(`${RCSB_API}/entry/${id}`, signal),
    fetchJson(`${RCSB_API}/polymer_entity/${id}/1`, signal),
  ])
  if (entry.status === "rejected") throw entry.reason as Error

  const data = (await entry.value.json()) as {
    struct?: { title?: string }
    exptl?: { method?: string }[]
    rcsb_entry_info?: { resolution_combined?: number[] }
    rcsb_accession_info?: { initial_release_date?: string }
    citation?: { rcsb_authors?: string[] }[]
  }

  let organism: string | null = null
  if (entity.status === "fulfilled") {
    const entityData = (await entity.value.json()) as {
      rcsb_entity_source_organism?: { scientific_name?: string }[]
    }
    organism = entityData.rcsb_entity_source_organism?.[0]?.scientific_name ?? null
  }

  const authors = data.citation?.[0]?.rcsb_authors
  return {
    title: data.struct?.title ?? null,
    experimentalMethod: data.exptl?.[0]?.method ?? null,
    resolutionAngstrom: data.rcsb_entry_info?.resolution_combined?.[0] ?? null,
    releasedDate: data.rcsb_accession_info?.initial_release_date ?? null,
    authors: authors?.length ? (authors.length > 1 ? `${authors[0]} et al.` : authors[0]) : null,
    organism,
  }
}

/** PDB entries are immutable — cache forever for the session. Disabled without an id. */
export function usePdbEntry(pdbId: string | undefined) {
  return useQuery({
    queryKey: ["rcsb", pdbId ?? ""],
    queryFn: ({ signal }) => fetchPdbEntry(pdbId ?? "", signal),
    enabled: pdbId !== undefined,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  })
}

import type { ExperimentSource } from "@/api/generated/models"

/** Display URL: scheme always stripped; doi.org prefix too — the DOI path is the identifier. */
function displayUrl(url: string): string {
  return url.replace(/^https?:\/\/(doi\.org\/)?/i, "")
}

/** One-line label for the title row and card footer; null when there is nothing worth showing. */
export function sourceLabel(source: ExperimentSource | null | undefined): string | null {
  if (!source) return null
  switch (source.type) {
    case "pdb":
      if (source.pdb_id) return `RCSB PDB (${source.pdb_id})`
      return source.url ? displayUrl(source.url) : null
    case "repo":
      return source.url ? displayUrl(source.url) : null
    case "file": {
      // Creation-time upload count; falls back to remaining files for old payloads.
      const count = source.file_count ?? source.files.length
      return count > 0 ? `Uploaded ${String(count)} file${count === 1 ? "" : "s"}` : null
    }
  }
}

export function sourceTypeLabel(source: ExperimentSource): string {
  switch (source.type) {
    case "pdb":
      return source.pdb_id ? "Protein Data Bank (RCSB)" : ("PDB file (direct URL)" as const)
    case "repo":
      return "External repository" as const
    case "file":
      return "File upload" as const
  }
}

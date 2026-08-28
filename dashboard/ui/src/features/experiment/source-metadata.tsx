import { useState } from "react"

import type { Experiment, FileInfo } from "@/api/generated/models"
import { formatBytes, formatDate } from "@/shared/format"
import { sourceLabel, sourceTypeLabel } from "@/shared/source"
import { Dialog, DialogContent, DialogHeader, DialogTitle, Skeleton } from "@e-infra/design-system"
import { Database, Dna, Download, ExternalLink, File as FileIcon, Upload } from "lucide-react"

import { PdbNotFoundError, usePdbEntry } from "./rcsb"

const SOURCE_ICONS = { pdb: Dna, repo: Database, file: Upload } as const

function SourceFilesList({ files }: { files: FileInfo[] }) {
  return (
    <ul className="divide-border divide-y rounded-md border">
      {files.map((file) => (
        <li key={file.path} className="flex items-center gap-3 px-3 py-2 text-sm">
          <FileIcon size={16} className="text-text-muted shrink-0" aria-hidden />
          <span className="truncate" title={file.name}>
            {file.name}
          </span>
          <span className="text-text-muted ml-auto shrink-0">{formatBytes(file.size)}</span>
          <a href={file.url} download aria-label={`Download ${file.name}`} className="hover:text-primary shrink-0">
            <Download size={16} aria-hidden />
          </a>
        </li>
      ))}
    </ul>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="text-text-muted w-32 shrink-0">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  )
}

function PdbSourceDialog({
  experiment,
  open,
  onOpenChange,
}: {
  experiment: Experiment
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const source = experiment.source
  const pdbId = source?.type === "pdb" ? source.pdb_id : undefined
  const query = usePdbEntry(pdbId)
  const entry = query.data
  const files = source?.files ?? []

  const rcsbUrl = pdbId ? `https://www.rcsb.org/structure/${pdbId}` : undefined
  const outbound = rcsbUrl ?? source?.url

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Experiment source</DialogTitle>
        </DialogHeader>
        {pdbId && query.isPending ? (
          <div className="space-y-2" aria-label="Loading PDB entry">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : (
          <dl className="space-y-2 text-sm">
            {source && <DetailRow label="Source">{sourceTypeLabel(source)}</DetailRow>}
            {pdbId && <DetailRow label="PDB ID">{pdbId}</DetailRow>}
            {entry?.title && <DetailRow label="Entry title">{entry.title}</DetailRow>}
            {entry?.experimentalMethod && <DetailRow label="Method">{entry.experimentalMethod}</DetailRow>}
            {entry?.resolutionAngstrom !== null && entry?.resolutionAngstrom !== undefined && (
              <DetailRow label="Resolution">{entry.resolutionAngstrom.toFixed(2)} Å</DetailRow>
            )}
            {entry?.organism && <DetailRow label="Organism">{entry.organism}</DetailRow>}
            {entry?.releasedDate && <DetailRow label="Released">{formatDate(entry.releasedDate)}</DetailRow>}
            {entry?.authors && <DetailRow label="Authors">{entry.authors}</DetailRow>}
            {!pdbId && source?.url && <DetailRow label="Downloaded from">{source.url}</DetailRow>}
          </dl>
        )}
        {pdbId && query.isError && (
          <p className="text-text-muted text-sm">
            {query.error instanceof PdbNotFoundError
              ? `Entry ${pdbId} was not found in RCSB PDB.`
              : "Couldn't reach RCSB PDB. Try again later."}
          </p>
        )}
        {files.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Structure files</h3>
            <SourceFilesList files={files} />
          </section>
        )}
        {outbound && (
          <p className="text-sm">
            <a
              href={outbound}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 hover:underline"
            >
              {rcsbUrl ? "Open in RCSB PDB" : "Open source URL"}
              <ExternalLink size={14} aria-hidden />
            </a>
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function FilesSourceDialog({
  experiment,
  open,
  onOpenChange,
}: {
  experiment: Experiment
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const files = experiment.source?.files ?? []
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Experiment source</DialogTitle>
        </DialogHeader>
        <dl className="space-y-2 text-sm">
          <DetailRow label="Source">File upload</DetailRow>
          <DetailRow label="Files">{files.length}</DetailRow>
        </dl>
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Uploaded files</h3>
          <SourceFilesList files={files} />
        </section>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Title-row source item: repo → outbound link, pdb/upload → info dialog.
 * Hidden for legacy experiments without a source.
 */
export function SourceItem({ experiment }: { experiment: Experiment }) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const source = experiment.source
  const label = sourceLabel(source)
  if (!source || !label) return null

  let value: React.ReactNode = label
  if (source.type === "repo" && source.url) {
    value = (
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
        {label}
      </a>
    )
  } else if (source.type === "pdb" || source.type === "file") {
    value = (
      <button type="button" onClick={() => setDialogOpen(true)} className="cursor-pointer hover:underline">
        {label}
      </button>
    )
  }

  const Icon = SOURCE_ICONS[source.type]

  return (
    <>
      <span className="flex max-w-52 items-center gap-1.5 truncate">
        <Icon size={14} aria-hidden className="shrink-0" />
        <span className="truncate">{value}</span>
      </span>
      {source.type === "pdb" ? (
        <PdbSourceDialog experiment={experiment} open={dialogOpen} onOpenChange={setDialogOpen} />
      ) : source.type === "file" ? (
        <FilesSourceDialog experiment={experiment} open={dialogOpen} onOpenChange={setDialogOpen} />
      ) : null}
    </>
  )
}

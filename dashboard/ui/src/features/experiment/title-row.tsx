import { useState } from "react"

import { toApiError } from "@/api/errors"
import { getGetExperimentQueryKey, getListExperimentsQueryKey, useUpdateExperiment } from "@/api/generated/client"
import type { Experiment } from "@/api/generated/models"
import { formatDate } from "@/shared/format"
import { sourceLabel } from "@/shared/source"
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  H1,
  Input,
  Label,
} from "@e-infra/design-system"
import { useQueryClient } from "@tanstack/react-query"
import { Calendar, GitBranch, Pencil } from "lucide-react"
import { toast } from "sonner"

import { SourceItem } from "./source-metadata"

/** "sb-ncbr/mddash-notebooks.git" from a full git URL (https or git@). */
function shortRepo(repo: string): string {
  const ssh = /^git@[^:]+:(.+)$/.exec(repo)
  if (ssh) return ssh[1]
  try {
    return new URL(repo).pathname.replace(/^\//, "")
  } catch {
    return repo
  }
}

export function TitleRow({ experiment }: { experiment: Experiment }) {
  const queryClient = useQueryClient()
  const [renameOpen, setRenameOpen] = useState(false)
  const [nextName, setNextName] = useState(experiment.name)

  const rename = useUpdateExperiment({
    mutation: {
      onSuccess: () => {
        toast.success("Experiment renamed")
        setRenameOpen(false)
        void queryClient.invalidateQueries({ queryKey: getGetExperimentQueryKey(experiment.id) })
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  function openRename() {
    setNextName(experiment.name)
    setRenameOpen(true)
  }

  function submitRename(event: React.FormEvent) {
    event.preventDefault()
    const name = nextName.trim()
    if (!name || name === experiment.name) return
    rename.mutate({ experimentId: experiment.id, data: { name } })
  }

  const items: React.ReactNode[] = [
    sourceLabel(experiment.source) ? <SourceItem key="source" experiment={experiment} /> : null,
    <span key="created" className="flex items-center gap-1.5">
      <Calendar size={14} aria-hidden className="shrink-0" />
      {formatDate(experiment.created_at)}
    </span>,
    experiment.notebooks_repo ? (
      <a
        key="repo"
        href={experiment.notebooks_repo}
        target="_blank"
        rel="noopener noreferrer"
        className="flex max-w-52 items-center gap-1.5 hover:underline"
        title={experiment.notebooks_repo}
      >
        <GitBranch size={14} aria-hidden className="shrink-0" />
        <span className="truncate">{shortRepo(experiment.notebooks_repo)}</span>
      </a>
    ) : null,
  ].filter((item) => item !== null)

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <H1>Experiment</H1>
      <Button
        variant="outline"
        size="sm"
        onClick={openRename}
        aria-label="Rename experiment"
        className="max-w-full min-w-0"
      >
        <span className="truncate">{experiment.name}</span>
        <Pencil aria-hidden="true" className="shrink-0" />
      </Button>
      {items.length > 0 && <span className="bg-border h-8 w-px" aria-hidden="true" />}
      <div className="text-text-muted flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {items.map((item, index) => (
          <span key={index} className="flex items-center gap-2">
            {index > 0 && <span aria-hidden="true">·</span>}
            {item}
          </span>
        ))}
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename experiment</DialogTitle>
          </DialogHeader>
          <form onSubmit={submitRename} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`rename-${experiment.id}`}>Name</Label>
              <Input
                id={`rename-${experiment.id}`}
                value={nextName}
                onChange={(event) => setNextName(event.target.value)}
                required
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenameOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={rename.isPending || !nextName.trim()}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

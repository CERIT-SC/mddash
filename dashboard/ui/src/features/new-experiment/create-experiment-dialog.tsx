import { useMemo, useState } from "react"

import { toApiError } from "@/api/errors"
import { getListExperimentsQueryKey, useCreateExperiment } from "@/api/generated/client"
import type { CreateExperimentForm, NotebookModule } from "@/api/generated/models"
import { ENGINE_LABELS } from "@/shared/engine"
import { formatBytes } from "@/shared/format"
import { CATEGORY_LABELS } from "@/shared/notebook-module"
import { HintTooltip } from "@/shared/ui/hint-tooltip"
import {
  Button,
  cn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  ToggleGroup,
  ToggleGroupItem,
} from "@e-infra/design-system"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { CircleCheck, CloudUpload, LoaderCircle, Trash2 } from "lucide-react"
import { useDropzone, type FileRejection } from "react-dropzone"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { CustomWorkflowIcon, ModuleIcon } from "./module-icon"

/** SSH (git@host:owner/repo.git) or HTTP(S) with a host. */
function isGitUrl(url: string): boolean {
  if (url.startsWith("git@") && url.includes(":")) return true
  try {
    const parsed = new URL(url)
    return ["http:", "https:"].includes(parsed.protocol) && Boolean(parsed.host)
  } catch {
    return false
  }
}

function buildSchema(requireRepo: boolean) {
  return z
    .object({
      name: z.string().trim().min(1, "Enter a name for the experiment"),
      engine: z.enum(["GMX", "AMBER"]),
      source: z.enum(["pdb", "file", "repo"]),
      pdb: z.string(),
      repoUrl: z.string(),
      notebooksRepo: z.string(),
      accessToken: z.string(),
      files: z.array(z.instanceof(File)),
    })
    .superRefine((values, ctx) => {
      if (values.source === "pdb" && values.pdb.trim() === "") {
        ctx.addIssue({ code: "custom", path: ["pdb"], message: "Enter a PDB ID or a URL to a PDB file" })
      }
      if (values.source === "repo" && values.repoUrl.trim() === "") {
        ctx.addIssue({ code: "custom", path: ["repoUrl"], message: "Enter a DOI or repository URL" })
      }
      if (values.source === "file" && values.files.length === 0) {
        ctx.addIssue({ code: "custom", path: ["files"], message: "Add at least one file" })
      }
      if (requireRepo && !isGitUrl(values.notebooksRepo.trim())) {
        ctx.addIssue({ code: "custom", path: ["notebooksRepo"], message: "Enter a valid git repository URL" })
      }
    })
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>

type UploadFieldProps = { value: File[]; onChange: (files: File[]) => void }

function UploadField({ value, onChange }: UploadFieldProps) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted, rejections: FileRejection[]) => {
      if (rejections.length > 0) toast.error(rejections[0].errors[0].message)
      if (accepted.length > 0) onChange([...value, ...accepted])
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <div className="space-y-2">
      <div
        {...getRootProps()}
        className={cn(
          "text-text-muted flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center transition-colors",
          isDragActive ? "border-primary bg-primary/10" : "hover:border-primary hover:bg-primary/5"
        )}
      >
        <input {...getInputProps()} aria-label="Upload files" className="sr-only" />
        <CloudUpload className="h-8 w-8" aria-hidden="true" />
        <p className="text-text text-sm font-medium">
          {isDragActive ? "Drop the files here…" : "Drop files here or click to browse"}
        </p>
      </div>
      {value.length > 0 && (
        <ul className="divide-border divide-y rounded-md border">
          {value.map((file, index) => (
            <li key={`${file.name}-${index}`} className="flex items-center gap-3 px-3 py-2">
              <CircleCheck className="text-success h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-sm">{file.name}</span>
              <span className="text-text-muted shrink-0 text-xs">{formatBytes(file.size)}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${file.name}`}
                onClick={() => onChange(value.filter((_, i) => i !== index))}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

type CreateExperimentDialogProps = {
  /** Which workflow the form configures; null unmounts the dialog and resets the form. */
  selection: NotebookModule | "custom" | null
  onClose: () => void
  defaultNotebooksRepo: string
}

/** Remounts on every selection change, so the form always starts fresh — no reset plumbing. */
export function CreateExperimentDialog({ selection, ...rest }: CreateExperimentDialogProps) {
  if (selection === null) return null
  return <CreateExperimentDialogInner selection={selection} {...rest} />
}

type InnerProps = Omit<CreateExperimentDialogProps, "selection"> & { selection: NotebookModule | "custom" }

function CreateExperimentDialogInner({ selection, onClose, defaultNotebooksRepo }: InnerProps) {
  const isCustom = selection === "custom"
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [tokenOpen, setTokenOpen] = useState(false)

  const schema = useMemo(() => buildSchema(isCustom), [isCustom])
  const form = useForm<FormValues>({
    resolver: standardSchemaResolver(schema),
    defaultValues: {
      name: "",
      engine: isCustom ? "GMX" : selection.engine,
      source: "pdb",
      pdb: "",
      repoUrl: "",
      notebooksRepo: defaultNotebooksRepo,
      accessToken: "",
      files: [],
    },
  })
  const source = form.watch("source")
  const notebooksRepoValue = form.watch("notebooksRepo")
  const isHttpsRepo = notebooksRepoValue.trim().startsWith("https://")

  const create = useCreateExperiment({
    mutation: {
      onSuccess: (response) => {
        toast.success(`Experiment “${response.data.name}” created`)
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
        onClose()
        void navigate({ to: "/experiments/$experimentId", params: { experimentId: response.data.id } })
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  function onSubmit(values: FormValues) {
    const data: CreateExperimentForm = { "experiment-name": values.name.trim(), type: values.source }
    if (values.source === "pdb") data.pdb = values.pdb.trim()
    if (values.source === "repo") data["repo-url"] = values.repoUrl.trim()
    if (values.source === "file") data["simulation-files"] = values.files
    if (isCustom) {
      const repo = values.notebooksRepo.trim()
      data["notebooks-repo"] = repo
      data.engine = values.engine
      if (repo.startsWith("https://") && values.accessToken.trim() !== "")
        data["access-token"] = values.accessToken.trim()
    } else {
      data["notebook-module"] = selection.id
      data.engine = selection.engine
    }
    create.mutate({ data })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      {/* grid-cols-[minmax(0,1fr)]: Radix/DS dialog grid auto-track would otherwise size to
          the max-content of nowrap children (truncated header text) and overflow horizontally */}
      <DialogContent className="max-h-[85dvh] grid-cols-[minmax(0,1fr)] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <span
              className="bg-surface text-text-muted flex h-11 w-11 shrink-0 items-center justify-center rounded-lg"
              aria-hidden="true"
            >
              {isCustom ? <CustomWorkflowIcon /> : <ModuleIcon category={selection.category} />}
            </span>
            <div className="min-w-0">
              <DialogTitle className="truncate">
                {/* colon, not parens: names may themselves contain parentheses ((BioBB) -> "()))") */}
                {isCustom ? "Custom workflow" : `New Experiment: ${selection.name}`}
              </DialogTitle>
              <DialogDescription className="truncate">
                {isCustom
                  ? "Any engine"
                  : `${CATEGORY_LABELS[selection.category]} · ${ENGINE_LABELS[selection.engine]}`}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" autoComplete="off">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter the name of the experiment" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {isCustom && (
              <FormField
                control={form.control}
                name="engine"
                render={({ field }) => (
                  <FormItem>
                    <div className="flex items-center gap-1.5">
                      <FormLabel>MD Engine</FormLabel>
                      <HintTooltip text="Simulation tools used by the experiment's notebooks." />
                    </div>
                    <FormControl>
                      <ToggleGroup
                        type="single"
                        value={field.value}
                        onValueChange={(value) => value && field.onChange(value)}
                        className="w-full"
                      >
                        <ToggleGroupItem value="GMX" className="flex-1">
                          GROMACS
                        </ToggleGroupItem>
                        <ToggleGroupItem value="AMBER" className="flex-1">
                          AMBER
                        </ToggleGroupItem>
                      </ToggleGroup>
                    </FormControl>
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="source"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center gap-1.5">
                    <FormLabel>Initial Data</FormLabel>
                    <HintTooltip text="How the experiment's starting structure and files are obtained." />
                  </div>
                  <FormControl>
                    <ToggleGroup
                      type="single"
                      value={field.value}
                      onValueChange={(value) => value && field.onChange(value)}
                      className="w-full"
                    >
                      <ToggleGroupItem value="pdb" className="flex-1">
                        PDB
                      </ToggleGroupItem>
                      <ToggleGroupItem value="file" className="flex-1">
                        Upload Files
                      </ToggleGroupItem>
                      <ToggleGroupItem value="repo" className="flex-1">
                        DOI / Repository
                      </ToggleGroupItem>
                    </ToggleGroup>
                  </FormControl>
                </FormItem>
              )}
            />

            {source === "pdb" && (
              <FormField
                control={form.control}
                name="pdb"
                render={({ field }) => (
                  <FormItem>
                    <div className="flex items-center gap-1.5">
                      <FormLabel>PDB ID or URL</FormLabel>
                      <HintTooltip text="RCSB PDB ID (e.g. 1ABC) or a direct URL to a .pdb file." />
                    </div>
                    <FormControl>
                      <Input placeholder="e.g. 1ABC or https://files.rcsb.org/download/1AKI.pdb" {...field} />
                    </FormControl>
                    <FormDescription>The structure will be downloaded from RCSB PDB.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {source === "repo" && (
              <FormField
                control={form.control}
                name="repoUrl"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>DOI or Repository URL</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. https://doi.org/10.5281/zenodo.…" {...field} />
                    </FormControl>
                    <FormDescription>
                      Supports any InvenioRDM repository (e.g. Zenodo, MDRepo) or a DOI link.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            {source === "file" && (
              <FormField
                control={form.control}
                name="files"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <UploadField value={field.value} onChange={field.onChange} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            {isCustom && (
              <>
                <FormField
                  control={form.control}
                  name="notebooksRepo"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Notebooks Repository</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormDescription>
                        Git repository with notebooks. Supports Binder and standard repos.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                {isHttpsRepo && (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() => setTokenOpen((prev) => !prev)}
                      aria-expanded={tokenOpen}
                      className="text-text-muted hover:text-text text-sm transition-colors"
                    >
                      {tokenOpen ? "Hide access token" : "Private repository? Provide an access token"}
                    </button>
                    {tokenOpen && (
                      <FormField
                        control={form.control}
                        name="accessToken"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Git Access Token</FormLabel>
                            <FormControl>
                              <Input type="password" placeholder="e.g. ghp_xxxxx, glpat_xxxxx" {...field} />
                            </FormControl>
                            <FormDescription>
                              Required for private HTTPS repositories. Only used for cloning, not stored.
                            </FormDescription>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                  </div>
                )}
              </>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending && <LoaderCircle className="animate-spin" aria-hidden="true" />}
                {create.isPending ? "Creating…" : "Create Experiment"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

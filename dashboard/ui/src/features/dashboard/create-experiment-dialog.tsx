import { useMemo, useState } from "react"

import { toApiError } from "@/api/errors"
import { getListExperimentsQueryKey, useCreateExperiment, useListNotebookModules } from "@/api/generated/client"
import type { CreateExperimentForm, Engine, NotebookModule } from "@/api/generated/models"
import { ENGINE_LABELS } from "@/shared/engine"
import { formatBytes } from "@/shared/format"
import {
  Badge,
  Button,
  cn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Skeleton,
  ToggleGroup,
  ToggleGroupItem,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@e-infra/design-system"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useQueryClient } from "@tanstack/react-query"
import {
  ChevronUp,
  CircleCheck,
  CircleHelp,
  CloudUpload,
  Code,
  FlaskConical,
  LoaderCircle,
  Plus,
  Trash2,
} from "lucide-react"
import { useDropzone, type FileRejection } from "react-dropzone"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

const ENGINE_ORDER: Engine[] = ["GMX", "AMBER"]

/** GMX workflows are preferred — sort them to the top, keeping catalog order otherwise. */
function sortModules(modules: NotebookModule[]): NotebookModule[] {
  return [...modules].sort((a, b) => ENGINE_ORDER.indexOf(a.engine) - ENGINE_ORDER.indexOf(b.engine))
}

/** SSH (git@host:owner/repo.git) or HTTP(S) with a host — mirrored from the old wizard. */
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

type PresetCardBodyProps = {
  icon: React.ReactNode
  name: string
  description?: string
  engines: Engine[]
  /** Slot rendered after the engine badges (e.g. a collapse chevron). */
  trailing?: React.ReactNode
}

function PresetCardBody({ icon, name, description, engines, trailing }: PresetCardBodyProps) {
  return (
    <>
      <span
        className="bg-surface text-text-muted flex h-11 w-11 shrink-0 items-center justify-center rounded-lg"
        aria-hidden="true"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block leading-tight font-medium">{name}</span>
        {description && <span className="text-text-muted block truncate text-sm">{description}</span>}
      </span>
      <span className="flex shrink-0 items-center gap-1.5">
        {engines.map((engine) => (
          <Badge key={engine} variant="secondary">
            {ENGINE_LABELS[engine]}
          </Badge>
        ))}
        {trailing}
      </span>
    </>
  )
}

type PresetCardProps = PresetCardBodyProps & { onSelect: () => void }

function PresetCard({ onSelect, ...body }: PresetCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="border-border hover:border-border-focus focus-visible:border-border-focus focus-visible:ring-border-focus/50 flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
    >
      <PresetCardBody {...body} />
    </button>
  )
}

type CreateExperimentDialogProps = { defaultNotebooksRepo: string }

export function CreateExperimentDialog({ defaultNotebooksRepo }: CreateExperimentDialogProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<NotebookModule | "custom" | null>(null)
  const [tokenOpen, setTokenOpen] = useState(false)

  const modules = useListNotebookModules({ query: { retry: false, enabled: open } })
  const presets = useMemo(() => sortModules(modules.data?.status === 200 ? modules.data.data : []), [modules.data])

  const isCustom = selected === "custom"
  const schema = useMemo(() => buildSchema(isCustom), [isCustom])
  const form = useForm<FormValues>({
    resolver: standardSchemaResolver(schema),
    defaultValues: {
      name: "",
      engine: "GMX",
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
  const showEngine = isCustom
  const isHttpsRepo = notebooksRepoValue.trim().startsWith("https://")

  const create = useCreateExperiment({
    mutation: {
      onSuccess: (response) => {
        toast.success(`Experiment “${response.data.name}” created`)
        void queryClient.invalidateQueries({ queryKey: getListExperimentsQueryKey() })
        handleOpenChange(false)
      },
      onError: (error) => toast.error(toApiError(error).message),
    },
  })

  function choose(next: NotebookModule | "custom") {
    setSelected(next)
    setTokenOpen(false)
    form.reset({
      name: "",
      engine: next === "custom" ? "GMX" : next.engine,
      source: "pdb",
      pdb: "",
      repoUrl: "",
      notebooksRepo: defaultNotebooksRepo,
      accessToken: "",
      files: [],
    })
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen)
    if (!nextOpen) {
      setSelected(null)
      setTokenOpen(false)
      form.reset()
    }
  }

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
    } else if (selected) {
      data["notebook-module"] = selected.id
      data.engine = selected.engine
    }
    create.mutate({ data })
  }

  const summaryName = selected === null ? "" : selected === "custom" ? "Custom" : selected.name
  const summaryDescription =
    selected === null || selected === "custom"
      ? "Use your own notebook repository and pick any engine."
      : (selected.description ?? undefined)
  const summaryEngines: Engine[] = selected === null ? [] : selected === "custom" ? ["GMX", "AMBER"] : [selected.engine]

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Plus size={16} /> New
        </Button>
      </DialogTrigger>
      {/* grid-cols-[minmax(0,1fr)]: Radix/DS dialog grid auto-track would otherwise size to
          the max-content of nowrap children (truncated descriptions) and overflow horizontally */}
      <DialogContent className="max-h-[85dvh] grid-cols-[minmax(0,1fr)] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>New Experiment</DialogTitle>
          <DialogDescription className="sr-only">
            Create an experiment from a preset workflow or a custom notebook repository.
          </DialogDescription>
        </DialogHeader>

        {selected === null ? (
          <div className="space-y-4">
            <section className="space-y-2">
              <h3 className="text-text-muted text-sm font-medium tracking-wide uppercase">Presets</h3>
              {modules.isPending && (
                <div className="space-y-2" aria-label="Loading presets">
                  <Skeleton className="h-17 w-full" />
                  <Skeleton className="h-17 w-full" />
                </div>
              )}
              {modules.isError && (
                <div className="space-y-2">
                  <p className="text-error text-sm">{toApiError(modules.error).message}</p>
                  <Button type="button" variant="outline" size="sm" onClick={() => void modules.refetch()}>
                    Retry
                  </Button>
                </div>
              )}
              {presets.map((module) => (
                <PresetCard
                  key={module.id}
                  icon={<FlaskConical size={20} />}
                  name={module.name}
                  description={module.description ?? undefined}
                  engines={[module.engine]}
                  onSelect={() => choose(module)}
                />
              ))}
            </section>
            <section className="space-y-2">
              <h3 className="text-text-muted text-sm font-medium tracking-wide uppercase">Custom</h3>
              <PresetCard
                icon={<Code size={20} />}
                name="Custom"
                description="Use your own notebook repository and pick any engine."
                engines={["GMX", "AMBER"]}
                onSelect={() => choose("custom")}
              />
            </section>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setSelected(null)}
              aria-expanded="true"
              aria-label="Choose a different preset"
              className="border-border hover:border-border-focus focus-visible:border-border-focus focus-visible:ring-border-focus/50 flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors focus-visible:ring-[3px] focus-visible:outline-none"
            >
              <PresetCardBody
                icon={isCustom ? <Code size={20} /> : <FlaskConical size={20} />}
                name={summaryName}
                description={summaryDescription}
                engines={summaryEngines}
                trailing={<ChevronUp size={18} aria-hidden="true" />}
              />
            </button>

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

                {showEngine && (
                  <FormField
                    control={form.control}
                    name="engine"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center gap-1.5">
                          <FormLabel>MD Engine</FormLabel>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button type="button" aria-label="MD engine help" className="text-text-muted">
                                <CircleHelp size={14} />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>Simulation tools used by the experiment's notebooks.</TooltipContent>
                          </Tooltip>
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
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button type="button" aria-label="Initial data help" className="text-text-muted">
                              <CircleHelp size={14} />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>
                            How the experiment's starting structure and files are obtained.
                          </TooltipContent>
                        </Tooltip>
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
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button type="button" aria-label="PDB help" className="text-text-muted">
                                <CircleHelp size={14} />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>RCSB PDB ID (e.g. 1ABC) or a direct URL to a .pdb file.</TooltipContent>
                          </Tooltip>
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
                  <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={create.isPending}>
                    {create.isPending && <LoaderCircle className="animate-spin" aria-hidden="true" />}
                    {create.isPending ? "Creating…" : "Create Experiment"}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </>
        )}

        {selected === null && (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="button" disabled title="Select a preset or the custom option first">
              Create Experiment
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

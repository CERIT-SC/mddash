import React, { useState } from "react"

import { useNavigate } from "@tanstack/react-router"
import { ChevronDown, ChevronUp, Loader2, RotateCcw } from "lucide-react"
import { toast } from "sonner"

import { DEFAULT_NOTEBOOKS_REPO, Engine } from "@/util/const"
import type { Engine as EngineType } from "@/util/const"
import { useCreateExperiment } from "@/hooks/use-experiments"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import Dropzone from "@/components/Dropzone"

const isValidGitUrl = (url: string): boolean => {
  // SSH format: git@host:owner/repo.git
  if (url.startsWith("git@") && url.includes(":")) {
    return true
  }
  // HTTPS format
  try {
    const parsed = new URL(url)
    return ["http:", "https:"].includes(parsed.protocol) && Boolean(parsed.host)
  } catch {
    return false
  }
}

const New = () => {
  const navigate = useNavigate()
  const createExperiment = useCreateExperiment()

  const [name, setName] = useState("")
  const [engine, setEngine] = useState<EngineType>(Engine.GMX)
  const [type, setType] = useState("")
  const [pdb, setPdb] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [notebooksRepo, setNotebooksRepo] = useState(DEFAULT_NOTEBOOKS_REPO)
  const [accessToken, setAccessToken] = useState("")
  const [showTokenInput, setShowTokenInput] = useState(false)

  const [nameError, setNameError] = useState(false)
  const [typeError, setTypeError] = useState(false)
  const [typeAuxError, setTypeAuxError] = useState(false)
  const [notebooksRepoError, setNotebooksRepoError] = useState(false)

  const isHttpsRepo = notebooksRepo.startsWith("http://") || notebooksRepo.startsWith("https://")

  const handleNotebooksRepoChange = (value: string) => {
    setNotebooksRepo(value)
    const isHttps = value.startsWith("http://") || value.startsWith("https://")
    if (!isHttps || value === DEFAULT_NOTEBOOKS_REPO) {
      setAccessToken("")
      setShowTokenInput(false)
    }
  }

  const validateForm = () => {
    let auxErr = false
    const notebooksInvalid = !isValidGitUrl(notebooksRepo)

    if ((type === "pdb" && !pdb) || (type === "repo" && !repoUrl) || (type === "file" && files.length === 0))
      auxErr = true

    setNameError(!name)
    setTypeError(!type)
    setTypeAuxError(auxErr)
    setNotebooksRepoError(notebooksInvalid)

    if (name && type && !auxErr && !notebooksInvalid) return true

    toast.error("Please fill in all required fields")
    return false
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (createExperiment.isPending || !validateForm()) return

    const formData = new FormData()
    formData.append("experiment-name", name)
    formData.append("engine", engine)
    formData.append("type", type)
    formData.append("notebooks-repo", notebooksRepo)
    if (type === "pdb") formData.append("pdb", pdb)
    if (type === "repo") formData.append("repo-url", repoUrl)
    if (type === "file" && files.length > 0) {
      files.forEach((file) => formData.append("simulation-files", file))
    }
    if (accessToken) formData.append("access-token", accessToken)

    createExperiment.mutate(formData, {
      onSuccess: (data) => {
        toast.success("Experiment created successfully!")
        navigate({ to: "/$id/wizard", params: { id: data.id } })
      },
    })
  }

  const handleTypeChange = (newType: string) => {
    setType(newType)
    setPdb("")
    setRepoUrl("")
    setFiles([])
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-center text-3xl font-bold">New Experiment</h1>

      <Card className="mx-auto w-full max-w-xl">
        <CardContent className="pt-6">
          <form autoComplete="off" onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-1">
              <Label htmlFor="experiment-name">Name</Label>
              <Input
                id="experiment-name"
                name="experiment-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={nameError ? "border-destructive" : ""}
              />
            </div>

            <div className="flex flex-col gap-1">
              <Label>MD Engine</Label>
              <Tabs value={engine} onValueChange={(v) => setEngine(v as EngineType)}>
                <TabsList className="w-full">
                  <TabsTrigger value={Engine.GMX} className="flex-1">
                    GROMACS
                  </TabsTrigger>
                  <TabsTrigger value={Engine.AMBER} className="flex-1">
                    AMBER
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            <div className="flex flex-col gap-2">
              <Label>Initial Data</Label>
              <Tabs value={type || ""} onValueChange={handleTypeChange}>
                <TabsList className="w-full">
                  <TabsTrigger value="file" className="flex-1">
                    Upload Files
                  </TabsTrigger>
                  <TabsTrigger value="pdb" className="flex-1">
                    PDB
                  </TabsTrigger>
                  <TabsTrigger value="repo" className="flex-1">
                    DOI / Repository
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              {(typeError || typeAuxError) && (
                <p className="text-destructive text-xs">Select a source and fill its required details.</p>
              )}
            </div>

            {type === "pdb" && (
              <div className="flex flex-col gap-1">
                <Label htmlFor="pdb">PDB ID or URL</Label>
                <Input
                  id="pdb"
                  value={pdb}
                  onChange={(e) => setPdb(e.target.value)}
                  placeholder="e.g. 1ABC or https://files.rcsb.org/download/1AKI.pdb"
                  className={typeAuxError ? "border-destructive" : ""}
                />
                <p className="text-muted-foreground text-xs">
                  Enter an RCSB PDB ID (e.g. 1ABC) or a direct URL to a PDB file
                </p>
              </div>
            )}
            {type === "repo" && (
              <div className="flex flex-col gap-1">
                <Label htmlFor="repo-url">DOI or Repository URL</Label>
                <Input
                  id="repo-url"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  className={typeAuxError ? "border-destructive" : ""}
                />
                <p className="text-muted-foreground text-xs">
                  Supports any InvenioRDM repository (e.g. Zenodo, MDRepo) or a DOI link
                </p>
              </div>
            )}
            {type === "file" && <Dropzone inputName="simulation-files" onFilesChange={setFiles} />}

            <div className="flex flex-col gap-2">
              <div className="flex flex-col gap-1">
                <Label htmlFor="notebooks-repo">Notebooks Repository</Label>
                <div className="flex gap-2">
                  <Input
                    id="notebooks-repo"
                    value={notebooksRepo}
                    onChange={(e) => handleNotebooksRepoChange(e.target.value)}
                    className={notebooksRepoError ? "border-destructive flex-1" : "flex-1"}
                  />
                  {notebooksRepo !== DEFAULT_NOTEBOOKS_REPO && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          onClick={() => handleNotebooksRepoChange(DEFAULT_NOTEBOOKS_REPO)}
                          aria-label="Reset to default"
                        >
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Reset to default</TooltipContent>
                    </Tooltip>
                  )}
                </div>
                <p className="text-muted-foreground text-xs">
                  {notebooksRepoError
                    ? "Enter a valid git repository"
                    : "Git repository with notebooks. Supports Binder and standard repos."}
                </p>
              </div>

              {notebooksRepo !== DEFAULT_NOTEBOOKS_REPO && isHttpsRepo && (
                <Collapsible open={showTokenInput} onOpenChange={setShowTokenInput}>
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-sm transition-colors"
                    >
                      {showTokenInput ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      {showTokenInput ? "Hide access token" : "Provide access token"}
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 flex flex-col gap-1">
                    <Label htmlFor="access-token">Git Access Token</Label>
                    <Input
                      id="access-token"
                      type="password"
                      value={accessToken}
                      onChange={(e) => setAccessToken(e.target.value)}
                      placeholder="e.g. ghp_xxxxx, glpat_xxxxx, github_pat_xxxxx"
                    />
                    <p className="text-muted-foreground text-xs">
                      Required for private HTTPS repositories. Not applicable for SSH URLs. Only used for cloning, not
                      stored.
                    </p>
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>

            <Button type="submit" disabled={createExperiment.isPending} className="self-start">
              {createExperiment.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {createExperiment.isPending ? "Creating..." : "Create Experiment"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

export default New

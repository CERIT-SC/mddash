import type { FileOption } from "@/util/types"

export type NotebookRole = "setup" | "analysis"

const ROLE_FILENAMES: Record<NotebookRole, string> = {
  setup: "setup.ipynb",
  analysis: "analysis.ipynb",
}

export function pickNotebookFile(role: NotebookRole, files: FileOption[] | undefined): FileOption | undefined {
  if (!files || files.length === 0) return undefined

  const desired = ROLE_FILENAMES[role]
  const other = ROLE_FILENAMES[role === "setup" ? "analysis" : "setup"]

  const matches = files.filter((f) => f.name.toLowerCase() === desired).sort((a, b) => a.path.localeCompare(b.path))
  if (matches.length >= 1) return matches[0]

  if (files.length === 1 && files[0].name.toLowerCase() !== other) return files[0]

  return undefined
}

export function buildNotebookUrl(notebookPath: string, token: string, relativePath: string): string {
  const base = notebookPath.split("?")[0]
  const encoded = relativePath.split("/").map(encodeURIComponent).join("/")
  return `${base}lab/tree/${encoded}?token=${token}`
}

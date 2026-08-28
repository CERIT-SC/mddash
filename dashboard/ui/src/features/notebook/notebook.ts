import type { FileInfo, Notebook } from "@/api/generated/models"

type NotebookRole = "setup" | "analysis"

const ROLE_FILENAMES: Record<NotebookRole, string> = {
  setup: "setup.ipynb",
  analysis: "analysis.ipynb",
}

/** Picks the notebook file for a role: the canonical name wins; a lone other notebook is a fallback. */
export function pickNotebookFile(role: NotebookRole, files: FileInfo[] | undefined): FileInfo | undefined {
  if (!files || files.length === 0) return undefined
  const desired = ROLE_FILENAMES[role]
  const other = ROLE_FILENAMES[role === "setup" ? "analysis" : "setup"]
  const matches = files
    .filter((file) => file.name.toLowerCase() === desired)
    .sort((a, b) => a.path.localeCompare(b.path))
  if (matches.length >= 1) return matches[0]
  if (files.length === 1 && files[0].name.toLowerCase() !== other) return files[0]
  return undefined
}

export function buildNotebookUrl(notebookPath: string, token: string, relativePath: string): string {
  const base = notebookPath.split("?")[0]
  const encoded = relativePath.split("/").map(encodeURIComponent).join("/")
  return `${base}lab/tree/${encoded}?token=${token}`
}

export function notebookRoleUrl(
  role: NotebookRole,
  files: FileInfo[] | undefined,
  notebook: Notebook | undefined
): string | undefined {
  if (notebook === undefined) return undefined
  const file = pickNotebookFile(role, files)
  return file ? buildNotebookUrl(notebook.path, notebook.token, file.path) : notebook.path
}

import { isNotebookActive } from "@/shared/pod-status"

import { NotebookControls } from "./notebook-controls"
import { useNotebook, useNotebookReady } from "./notebook-hooks"

type NotebookStatusBarProps = { experimentId: string }

export function NotebookStatusBar({ experimentId }: NotebookStatusBarProps) {
  const notebookQuery = useNotebook(experimentId)
  const notebook = notebookQuery.data?.status === 200 ? notebookQuery.data.data : undefined
  const { ready, probeFailures } = useNotebookReady(experimentId, notebook)

  // The bar exists only while the notebook is up; loading, errors, and
  // DOWN/ERROR leave the slot empty (start lives with the simulation setup).
  if (notebook === undefined || !isNotebookActive(notebook.status)) return null

  return (
    <section
      aria-label="Notebook status"
      className="border-border bg-surface mx-auto w-fit max-w-full rounded-b-lg border border-t-0 shadow-md"
    >
      <NotebookControls experimentId={experimentId} notebook={notebook} ready={ready} probeFailures={probeFailures} />
    </section>
  )
}

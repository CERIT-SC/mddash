import type { ReactElement } from "react"
import { StrictMode } from "react"

import { createRoot } from "react-dom/client"

import "../index.css"

/** Mount a page component the same way every JupyterHub entry does. */
export function mount(node: ReactElement) {
  const el = document.getElementById("root")
  if (!el) throw new Error("No #root element")
  createRoot(el).render(<StrictMode>{node}</StrictMode>)
}

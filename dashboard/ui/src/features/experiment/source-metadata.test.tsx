import { experiment } from "@/shared/fixtures/experiment"
import { mockApiBySuffix } from "@/shared/fixtures/mock-fetch"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { SourceItem } from "./source-metadata"

function renderItem(exp: ReturnType<typeof experiment>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SourceItem experiment={exp} />
    </QueryClientProvider>
  )
}

describe("SourceItem", () => {
  it("renders repo sources as plain outbound links", () => {
    renderItem(experiment("e1", { source: { type: "repo", url: "https://zenodo.org/records/7261108", files: [] } }))
    const link = screen.getByRole("link", { name: "zenodo.org/records/7261108" })
    expect(link).toHaveAttribute("href", "https://zenodo.org/records/7261108")
    expect(link).toHaveAttribute("target", "_blank")
  })

  it("renders nothing for legacy experiments without source", () => {
    const { container } = renderItem(experiment("e2", { source: null }))
    expect(container).toBeEmptyDOMElement()
  })

  it("opens the PDB dialog with fetched entry data and file downloads", async () => {
    mockApiBySuffix({
      "/entry/1LYZ": Response.json({
        struct: { title: "NATIVE MINIPROTEIN" },
        exptl: [{ method: "X-RAY DIFFRACTION" }],
        rcsb_entry_info: { resolution_combined: [1.2] },
        rcsb_accession_info: { initial_release_date: "1974-04-05T00:00:00Z" },
        citation: [{ rcsb_authors: ["Diamond, R.", "Konarev, P."] }],
      }),
      "/polymer_entity/1LYZ/1": Response.json({
        rcsb_entity_source_organism: [{ scientific_name: "Gallus gallus" }],
      }),
    })
    renderItem(
      experiment("e3", {
        source: {
          type: "pdb",
          pdb_id: "1LYZ",
          files: [
            { name: "input.pdb", size: 2048, path: "input.pdb", url: "/dash/api/experiments/e3/files/input.pdb" },
          ],
        },
      })
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "RCSB PDB (1LYZ)" }))

    expect(await screen.findByText("NATIVE MINIPROTEIN")).toBeVisible()
    expect(screen.getByText("X-RAY DIFFRACTION")).toBeVisible()
    expect(screen.getByText("1.20 Å")).toBeVisible()
    expect(screen.getByText("Gallus gallus")).toBeVisible()
    expect(screen.getByText("Apr 5, 1974")).toBeVisible()
    expect(screen.getByText("Diamond, R. et al.")).toBeVisible()

    const download = screen.getByRole("link", { name: "Download input.pdb" })
    expect(download).toHaveAttribute("href", "/dash/api/experiments/e3/files/input.pdb")
    expect(download).toHaveAttribute("download")
    expect(screen.getByRole("link", { name: /Open in RCSB PDB/ })).toHaveAttribute(
      "href",
      "https://www.rcsb.org/structure/1LYZ"
    )
  })

  it("shows a not-found note for unknown PDB ids, keeping file downloads", async () => {
    mockApiBySuffix({})
    renderItem(
      experiment("e4", {
        source: {
          type: "pdb",
          pdb_id: "ZZZZ",
          files: [{ name: "input.pdb", size: 1, path: "input.pdb", url: "/dash/api/experiments/e4/files/input.pdb" }],
        },
      })
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "RCSB PDB (ZZZZ)" }))
    expect(await screen.findByText(/not found in RCSB PDB/)).toBeVisible()
    expect(screen.getByRole("link", { name: "Download input.pdb" })).toBeVisible()
  })

  it("labels direct-URL PDB sources without claiming RCSB provenance", async () => {
    renderItem(
      experiment("e6", {
        source: {
          type: "pdb",
          url: "https://example.org/models/xyz.pdb",
          files: [{ name: "input.pdb", size: 1, path: "input.pdb", url: "/dash/api/experiments/e6/files/input.pdb" }],
        },
      })
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "example.org/models/xyz.pdb" }))

    expect(await screen.findByRole("heading", { name: "Experiment source" })).toBeVisible()
    expect(screen.getByText("PDB file (direct URL)")).toBeVisible()
    expect(screen.getByText("https://example.org/models/xyz.pdb")).toBeVisible()
    expect(screen.getByRole("link", { name: /Open source URL/ })).toHaveAttribute(
      "href",
      "https://example.org/models/xyz.pdb"
    )
    expect(screen.queryByText(/RCSB/)).not.toBeInTheDocument()
    expect(screen.queryByText("PDB ID")).not.toBeInTheDocument()
  })

  it("opens the uploaded-files dialog for upload sources", async () => {
    renderItem(
      experiment("e5", {
        source: {
          type: "file",
          files: [
            { name: "gpcr.tpr", size: 3000, path: "gpcr.tpr", url: "/dash/api/experiments/e5/files/gpcr.tpr" },
            {
              name: "structure.pdb",
              size: 1500,
              path: "structure.pdb",
              url: "/dash/api/experiments/e5/files/structure.pdb",
            },
          ],
        },
      })
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole("button", { name: "Uploaded 2 files" }))

    expect(await screen.findByRole("heading", { name: "Experiment source" })).toBeVisible()
    expect(screen.getByText("gpcr.tpr")).toBeVisible()
    expect(screen.getByText("structure.pdb")).toBeVisible()
    expect(screen.getAllByRole("link", { name: /Download/ })).toHaveLength(2)
  })
})

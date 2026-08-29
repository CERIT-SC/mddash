import type { NotebookModuleCategory } from "@/api/generated/models"

export const CATEGORY_LABELS: Record<NotebookModuleCategory, string> = {
  protein: "Protein",
  "membrane-protein": "Membrane protein",
  "nucleic-acids": "Nucleic acids",
  "protein-ligand": "Protein–ligand",
  "small-molecule": "Small molecule",
  carbohydrate: "Carbohydrate",
  polymer: "Polymer",
}

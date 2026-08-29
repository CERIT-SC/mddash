import type { NotebookModule } from "@/api/generated/models"

/**
 * The bundled catalog, verbatim from dashboard/api/notebook-modules.json;
 * duplicate names across engines exercise grouping and disambiguation.
 */
export const CATALOG_MODULES: NotebookModule[] = [
  {
    id: "gromacs-protein",
    name: "Protein",
    description: "Prepare and analyze a solvated protein with GROMACS. A solid default for single-chain proteins.",
    engine: "GMX",
    author: "e-INFRA",
    category: "protein",
  },
  {
    id: "amber-protein",
    name: "Protein",
    description: "Prepare and analyze a solvated protein with AMBER. A solid default for single-chain proteins.",
    engine: "AMBER",
    author: "e-INFRA",
    category: "protein",
  },
  {
    id: "biobb-protein-gmx",
    name: "Protein (BioBB)",
    description:
      "Set up a solvated protein system using BioExcel Building Blocks and GROMACS. A modular, reproducible pipeline.",
    engine: "GMX",
    author: "BioBB",
    category: "protein",
  },
  {
    id: "biobb-protein-amber",
    name: "Protein (BioBB)",
    description:
      "Set up a solvated protein system using BioExcel Building Blocks and AmberTools. A modular, reproducible pipeline.",
    engine: "AMBER",
    author: "BioBB",
    category: "protein",
  },
  {
    id: "biobb-membrane-gmx",
    name: "Membrane protein (BioBB)",
    description: "Set up a membrane-embedded protein system using BioExcel Building Blocks and GROMACS.",
    engine: "GMX",
    author: "BioBB",
    category: "membrane-protein",
  },
]

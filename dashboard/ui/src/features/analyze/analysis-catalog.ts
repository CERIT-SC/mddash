import { AnalysisJobRequestAnalysis, AnalysisJobRequestPreprocessingMode } from "@/api/generated/models"

/**
 * Catalog of analyses a simulation can produce, keyed by the generated
 * contract enum. `resultName` is the normalized mwf output file name — it
 * differs from `value` only where mwf's task name and output name disagree.
 */

export interface AnalysisInfo {
  value: AnalysisJobRequestAnalysis
  label: string
  resultName: string
  /** True when mwf produces both a summary file and numbered variants (base-00, base-01, …). */
  hasVariants?: boolean
}

export const AVAILABLE_ANALYSES: AnalysisInfo[] = [
  // Standard — work with structure + trajectory alone
  { value: AnalysisJobRequestAnalysis.rmsds, label: "RMSD", resultName: "rmsds" },
  { value: AnalysisJobRequestAnalysis.rgyr, label: "Radius of Gyration", resultName: "rgyr" },
  { value: AnalysisJobRequestAnalysis.rmsf, label: "RMSF (Fluctuation)", resultName: "fluctuation" },
  { value: AnalysisJobRequestAnalysis.pca, label: "PCA", resultName: "pca" },
  { value: AnalysisJobRequestAnalysis.clusters, label: "Clusters", resultName: "clusters", hasVariants: true },
  {
    value: AnalysisJobRequestAnalysis.pairwise,
    label: "Pairwise RMSD",
    resultName: "rmsd-pairwise",
    hasVariants: true,
  },
  { value: AnalysisJobRequestAnalysis.hbonds, label: "Hydrogen Bonds", resultName: "hbonds", hasVariants: true },
  { value: AnalysisJobRequestAnalysis.sas, label: "SASA", resultName: "sasa" },
  { value: AnalysisJobRequestAnalysis.pockets, label: "Pockets", resultName: "pockets" },
  { value: AnalysisJobRequestAnalysis.tmscore, label: "TM-Scores", resultName: "tmscores" },
  {
    value: AnalysisJobRequestAnalysis.dist,
    label: "Distance Per Residue",
    resultName: "dist-perres",
    hasVariants: true,
  },
  // Runnable per the API enum (AnalysisType.PERRES → mwf 'perres'); the catalog
  // covers every submittable analysis so wizard and card counts agree.
  { value: AnalysisJobRequestAnalysis.perres, label: "RMSD Per Residue", resultName: "rmsd-perres" },
  { value: AnalysisJobRequestAnalysis.inter, label: "Interactions", resultName: "interactions" },
  // Membrane — auto-detected from structure; skipped if no lipid bilayer present
  { value: AnalysisJobRequestAnalysis.density, label: "Density Profile", resultName: "density" },
  { value: AnalysisJobRequestAnalysis.thickness, label: "Thickness", resultName: "thickness" },
  { value: AnalysisJobRequestAnalysis.apl, label: "Area Per Lipid", resultName: "apl" },
  { value: AnalysisJobRequestAnalysis.lorder, label: "Lipid Order", resultName: "lipid-order" },
  { value: AnalysisJobRequestAnalysis.linter, label: "Lipid Interactions", resultName: "lipid-inter" },
  {
    value: AnalysisJobRequestAnalysis.energies,
    label: "Energies",
    resultName: "energies",
    hasVariants: true,
  },
]

export interface PreprocessingOption {
  value: AnalysisJobRequestPreprocessingMode
  label: string
}

export const PREPROCESSING_OPTIONS: PreprocessingOption[] = [
  { value: AnalysisJobRequestPreprocessingMode.as_is, label: "Use Files As-Is" },
  { value: AnalysisJobRequestPreprocessingMode.image, label: "Image Only" },
  { value: AnalysisJobRequestPreprocessingMode.image_fit, label: "Image and Fit" },
]

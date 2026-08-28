import type {
  Analysis,
  AreaPerLipidAnalysis,
  ClustersAnalysis,
  DensityProfileAnalysis,
  DistancePerResidueAnalysis,
  EnergiesAgentData,
  EnergiesAnalysis,
  FluctuationAnalysis,
  HydrogenBondsAnalysis,
  InteractionData,
  LipidInteractionAnalysis,
  LipidOrderAnalysis,
  MembraneMapAnalysis,
  PCAAnalysis,
  PocketsAnalysis,
  RadiusOfGyrationAnalysis,
  RMSDAnalysis,
  RMSDPairwiseAnalysis,
  RMSDPairwiseMatrix,
  RMSDPerResidueAnalysis,
  RMSDPerResidueMatrixAnalysis,
  RMSDsAnalysis,
  SolventAccessibleSurfaceAnalysis,
  StatisticalData,
  ThicknessAnalysis,
  TMScoresAnalysis,
} from "../analysis-types"
import type { LineSeries } from "../charts/line-chart"
import type { StackedSeries } from "../charts/stacked-area-chart"

function hasStatSeries(
  obj: unknown,
  ...keys: string[]
): obj is {
  start?: number
  step?: number
  y: Record<string, StatisticalData>
} {
  if (!obj || typeof obj !== "object") return false
  const o = obj as { y?: unknown }
  if (!o.y || typeof o.y !== "object") return false
  const y = o.y as Record<string, unknown>
  if (keys.length === 0) return false
  return keys.every((key) => {
    const stat = y[key] as { data?: unknown } | undefined
    return !!stat && Array.isArray(stat.data)
  })
}

const isRmsdPairwiseMatrix = (obj: unknown): obj is RMSDPairwiseMatrix => {
  if (!obj || typeof obj !== "object") return false
  const matrix = obj as { name?: unknown; rmsds?: unknown }
  return (
    typeof matrix.name === "string" &&
    Array.isArray(matrix.rmsds) &&
    matrix.rmsds.length > 0 &&
    Array.isArray(matrix.rmsds[0])
  )
}

const isLegacyRmsdPairwise = (
  obj: unknown
): obj is {
  start?: number
  step?: number
  name?: string
  rmsds: number[][]
} => {
  if (!obj || typeof obj !== "object") return false
  const legacy = obj as { name?: unknown; rmsds?: unknown }
  return (
    typeof legacy.name === "string" &&
    Array.isArray(legacy.rmsds) &&
    legacy.rmsds.length > 0 &&
    Array.isArray(legacy.rmsds[0])
  )
}

function isRmsdPairwise(obj: unknown): obj is RMSDPairwiseAnalysis {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as RMSDPairwiseAnalysis
  return (
    typeof payload.start === "number" &&
    typeof payload.step === "number" &&
    Array.isArray(payload.data) &&
    payload.data.length > 0 &&
    payload.data.every(isRmsdPairwiseMatrix)
  )
}

export function isRmsdsAnalysis(obj: unknown): obj is RMSDsAnalysis {
  if (!obj || typeof obj !== "object") return false
  const o = obj as { data?: unknown }
  if (!Array.isArray(o.data) || o.data.length === 0) return false
  const first = o.data[0] as {
    reference?: unknown
    group?: unknown
    values?: unknown
  }
  return typeof first.reference === "string" && typeof first.group === "string" && Array.isArray(first.values)
}

export const isRmsdAnalysis = (obj: Analysis): obj is RMSDAnalysis => hasStatSeries(obj, "rmsd")

export const isRadiusOfGyrationAnalysis = (obj: Analysis): obj is RadiusOfGyrationAnalysis =>
  hasStatSeries(obj, "rgyr", "rgyrx", "rgyry", "rgyrz")

export const extractRmsdPairwiseAnalysis = (obj: Analysis): RMSDPairwiseAnalysis | undefined => {
  if (isRmsdPairwise(obj)) {
    return obj
  }

  if (obj && typeof obj === "object" && Array.isArray((obj as { data?: unknown }).data)) {
    const container = obj as {
      data: unknown[]
      start?: number
      step?: number
    }
    const matrices = container.data.filter(isRmsdPairwiseMatrix)
    if (matrices.length > 0) {
      return {
        start: typeof container.start === "number" ? container.start : 0,
        step: typeof container.step === "number" ? container.step : 1,
        data: matrices,
      }
    }
  }

  if (isLegacyRmsdPairwise(obj)) {
    const legacy = obj as {
      start?: number
      step?: number
      name?: string
      rmsds: number[][]
    }
    return {
      start: typeof legacy.start === "number" ? legacy.start : 0,
      step: typeof legacy.step === "number" ? legacy.step : 1,
      data: [
        {
          name: typeof legacy.name === "string" ? legacy.name : "Overall",
          rmsds: legacy.rmsds,
        },
      ],
    }
  }

  return undefined
}

export const isFluctuationAnalysis = (obj: Analysis): obj is FluctuationAnalysis => hasStatSeries(obj, "rmsf")

const isRmsdPerResidueSeries = (obj: unknown): obj is { name: string; rmsds: number[] } => {
  if (!obj || typeof obj !== "object") return false
  const series = obj as { name?: unknown; rmsds?: unknown }
  return (
    typeof series.name === "string" &&
    Array.isArray(series.rmsds) &&
    series.rmsds.length > 0 &&
    series.rmsds.every((value) => typeof value === "number")
  )
}

const isRmsdPerResidueMatrix = (obj: unknown): obj is RMSDPerResidueMatrixAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const matrix = obj as { rmsdpr?: unknown }
  return (
    Array.isArray(matrix.rmsdpr) &&
    matrix.rmsdpr.length > 0 &&
    matrix.rmsdpr.every((row) => Array.isArray(row) && row.every((value) => typeof value === "number"))
  )
}

function isRmsdPerResidueAnalysis(obj: Analysis): obj is RMSDPerResidueAnalysis {
  if (!obj || typeof obj !== "object") return false
  const data = (obj as RMSDPerResidueAnalysis).data
  if (!Array.isArray(data) || data.length === 0) return false
  return data.every(isRmsdPerResidueSeries)
}

export const extractRmsdPerResidueAnalysis = (obj: Analysis): RMSDPerResidueAnalysis | undefined => {
  if (isRmsdPerResidueAnalysis(obj)) {
    return obj
  }

  if (isRmsdPerResidueMatrix(obj)) {
    const matrix = obj as RMSDPerResidueMatrixAnalysis
    const data = matrix.rmsdpr.map((row, index) => ({
      name: `Residue ${index + 1}`,
      rmsds: row,
    }))
    return {
      step: matrix.step,
      data,
    }
  }

  return undefined
}

export function isTMScoresAnalysis(obj: Analysis): obj is TMScoresAnalysis {
  if (!obj || typeof obj !== "object") return false
  const data = (obj as TMScoresAnalysis).data
  if (!Array.isArray(data) || data.length === 0) return false
  const first = data[0]
  return (
    typeof first?.reference === "string" &&
    typeof first?.group === "string" &&
    Array.isArray(first?.values) &&
    first.values.length > 0
  )
}

const isPcaShape = (obj: unknown): obj is PCAAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const data = obj as PCAAnalysis
  return (
    Array.isArray(data.eigenvalues) &&
    data.eigenvalues.length > 0 &&
    Array.isArray(data.projections) &&
    data.projections.length > 0 &&
    Array.isArray(data.projections[0]) &&
    data.projections[0].length >= 2
  )
}

export const extractPcaAnalysis = (obj: Analysis): PCAAnalysis | undefined => {
  if (isPcaShape(obj)) {
    return obj
  }

  if (obj && typeof obj === "object" && isPcaShape((obj as { data?: unknown }).data)) {
    return (obj as unknown as { data: PCAAnalysis }).data
  }

  return undefined
}

export const isPocketsAnalysis = (obj: Analysis): obj is PocketsAnalysis => {
  if (!obj || typeof obj !== "object") return false
  return Array.isArray((obj as PocketsAnalysis).data)
}

export const isSasaAnalysis = (obj: Analysis): obj is SolventAccessibleSurfaceAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const analysis = obj as SolventAccessibleSurfaceAnalysis
  return Array.isArray(analysis.saspf)
}

const isNumericMatrix = (matrix: unknown): matrix is number[][] =>
  Array.isArray(matrix) &&
  matrix.length > 0 &&
  matrix.every(
    (row) =>
      Array.isArray(row) && row.length > 0 && row.every((value) => typeof value === "number" && Number.isFinite(value))
  )

const isDistancePerResidueAnalysis = (obj: Analysis): obj is DistancePerResidueAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const dataset = (obj as DistancePerResidueAnalysis).data
  if (!Array.isArray(dataset) || dataset.length === 0) return false
  return dataset.every(
    (entry) =>
      entry &&
      typeof entry === "object" &&
      typeof entry.name === "string" &&
      isNumericMatrix(entry.means) &&
      isNumericMatrix(entry.stdvs)
  )
}

const normalizeNumericMatrix = (matrix: unknown): number[][] => {
  if (!Array.isArray(matrix)) return []
  const sanitized: number[][] = []
  matrix.forEach((row) => {
    if (!Array.isArray(row)) return
    const sanitizedRow = row.map((value) => (typeof value === "number" && Number.isFinite(value) ? value : 0))
    sanitized.push(sanitizedRow)
  })
  return sanitized.length ? sanitized : []
}

const normalizeDistanceEntry = (
  entry: unknown,
  index: number
): DistancePerResidueAnalysis["data"][number] | undefined => {
  if (!entry || typeof entry !== "object") return undefined
  const record = entry as { name?: unknown; means?: unknown; stdvs?: unknown }
  const name =
    typeof record.name === "string" && record.name.trim().length ? record.name.trim() : `Interaction ${index + 1}`
  const means = normalizeNumericMatrix(record.means)
  const stdvs = normalizeNumericMatrix(record.stdvs)

  if (!means.length && !stdvs.length) {
    return undefined
  }

  return {
    name,
    means,
    stdvs,
  }
}

const distancePerResidueCache = new WeakMap<object, DistancePerResidueAnalysis>()

export const extractDistancePerResidueAnalysis = (obj: Analysis): DistancePerResidueAnalysis | undefined => {
  if (isDistancePerResidueAnalysis(obj)) {
    return obj
  }

  if (!obj || typeof obj !== "object") return undefined

  const cached = distancePerResidueCache.get(obj as object)
  if (cached) return cached

  const payload = obj as { data?: unknown }
  const sources: unknown[] = []

  if (Array.isArray(payload.data) && payload.data.length) {
    sources.push(...payload.data)
  } else {
    sources.push(obj)
  }

  const normalized = sources
    .map((entry, index) => normalizeDistanceEntry(entry, index))
    .filter((entry): entry is DistancePerResidueAnalysis["data"][number] => Boolean(entry))

  if (!normalized.length) return undefined

  const result: DistancePerResidueAnalysis = { data: normalized }
  distancePerResidueCache.set(obj as object, result)
  return result
}

export const isAreaPerLipidAnalysis = (obj: Analysis): obj is AreaPerLipidAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as AreaPerLipidAnalysis
  const data = payload.data as AreaPerLipidAnalysis["data"] | undefined
  if (!data || typeof data !== "object") return false
  const upper = (data as { [key: string]: unknown })["upper leaflet"]
  const lower = (data as { [key: string]: unknown })["lower leaflet"]
  return isNumericMatrix(upper) || isNumericMatrix(lower)
}

const isHydrogenBondsAnalysis = (obj: Analysis): obj is HydrogenBondsAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const dataset = (obj as HydrogenBondsAnalysis).data
  if (!Array.isArray(dataset) || dataset.length === 0) return false
  return dataset.every((entry) => {
    if (!entry || typeof entry !== "object") return false
    const payload = entry as HydrogenBondsAnalysis["data"][number]
    return (
      typeof payload.name === "string" &&
      Array.isArray(payload.acceptors) &&
      Array.isArray(payload.donors) &&
      Array.isArray(payload.hydrogens) &&
      Array.isArray(payload.hbonds) &&
      payload.hbonds.every((row) => Array.isArray(row) && row.every((value) => typeof value === "boolean"))
    )
  })
}

/** Finite numbers only — drops NaN/Infinity and non-numeric junk from upstream payloads. */
export const sanitizeNumericArray = (values: unknown): number[] =>
  Array.isArray(values)
    ? values.filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    : []

/** Pair x/y values into a line series, dropping non-finite points; undefined when empty. */
export const buildLineSeries = (label: string, xValues: number[], yValues: number[]): LineSeries | undefined => {
  if (!xValues.length || !yValues.length) return undefined
  const limit = Math.min(xValues.length, yValues.length)
  const data: Array<[number, number]> = []
  for (let i = 0; i < limit; i += 1) {
    const x = xValues[i]
    const y = yValues[i]
    if (Number.isFinite(x) && Number.isFinite(y)) {
      data.push([x, y])
    }
  }
  return data.length ? { name: label, data } : undefined
}

/** Same pairing for stacked area series (identical shape). */
export const buildStackedSeries = (label: string, xValues: number[], yValues: number[]): StackedSeries | undefined =>
  buildLineSeries(label, xValues, yValues)

const toBooleanMatrix = (matrix: unknown): boolean[][] => {
  if (!Array.isArray(matrix)) return []
  const normalized: boolean[][] = []
  matrix.forEach((row) => {
    if (!Array.isArray(row)) return
    const normalizedRow = row.map((value) => {
      if (typeof value === "boolean") return value
      if (typeof value === "number" && Number.isFinite(value)) {
        return value !== 0
      }
      return false
    })
    normalized.push(normalizedRow)
  })
  return normalized.length ? normalized : []
}

const normalizeLegacyHydrogenEntry = (
  entry: unknown,
  index: number
): HydrogenBondsAnalysis["data"][number] | undefined => {
  if (!entry || typeof entry !== "object") return undefined
  const record = entry as {
    name?: unknown
    acceptors?: unknown
    donors?: unknown
    hydrogens?: unknown
    hbonds?: unknown
    hbonds_timed?: unknown
  }

  const name =
    typeof record.name === "string" && record.name.trim().length ? record.name.trim() : `Interaction ${index + 1}`

  const hbondsMatrix = (() => {
    const directMatrix = toBooleanMatrix(record.hbonds)
    if (directMatrix.length) return directMatrix
    return toBooleanMatrix(record.hbonds_timed)
  })()

  const acceptors = sanitizeNumericArray(record.acceptors)
  const donors = sanitizeNumericArray(record.donors)
  const hydrogens = sanitizeNumericArray(record.hydrogens)

  if (!acceptors.length && !donors.length && !hydrogens.length && !hbondsMatrix.length) {
    return undefined
  }

  return {
    name,
    acceptors,
    donors,
    hydrogens,
    hbonds: hbondsMatrix,
  }
}

export const extractHydrogenBondsAnalysis = (obj: Analysis): HydrogenBondsAnalysis | undefined => {
  if (isHydrogenBondsAnalysis(obj)) {
    return obj
  }

  if (!obj || typeof obj !== "object") return undefined

  const payload = obj as { data?: unknown }
  const sources: unknown[] = []

  if (Array.isArray(payload.data) && payload.data.length) {
    sources.push(...payload.data)
  } else {
    sources.push(obj)
  }

  const normalized = sources
    .map((entry, index) => normalizeLegacyHydrogenEntry(entry, index))
    .filter((entry): entry is HydrogenBondsAnalysis["data"][number] => Boolean(entry))

  if (!normalized.length) return undefined

  return { data: normalized }
}

export const isLipidInteractionAnalysis = (obj: Analysis): obj is LipidInteractionAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as LipidInteractionAnalysis
  const dataset = payload.data
  if (!dataset || typeof dataset !== "object") return false
  const residues = (dataset as { residue_indices?: unknown }).residue_indices
  if (!Array.isArray(residues) || residues.length === 0) return false
  const lipidEntries = Object.entries(dataset).filter(([key]) => key !== "residue_indices")
  if (!lipidEntries.length) return false
  return lipidEntries.some(
    ([, values]) => Array.isArray(values) && values.some((value) => typeof value === "number" && Number.isFinite(value))
  )
}

export const isThicknessAnalysis = (obj: Analysis): obj is ThicknessAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as ThicknessAnalysis
  const dataset = payload.data
  if (!dataset || typeof dataset !== "object") return false
  const hasThicknessArray = Array.isArray(dataset.thickness) && dataset.thickness.length > 0
  if (!hasThicknessArray) return false
  return dataset.thickness.some((value) => typeof value === "number" && Number.isFinite(value))
}

export const isDensityProfileAnalysis = (obj: Analysis): obj is DensityProfileAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as DensityProfileAnalysis
  const dataset = payload.data
  if (!dataset || typeof dataset !== "object") return false
  const { comps, z } = dataset as {
    comps?: unknown
    z?: unknown
  }
  if (!Array.isArray(z) || !z.length) return false
  if (!Array.isArray(comps) || !comps.length) return false
  return comps.every((component) => {
    if (!component || typeof component !== "object") return false
    const section = component as {
      number?: { dens?: unknown }
      mass?: { dens?: unknown }
      charge?: { dens?: unknown }
      electron?: { dens?: unknown }
    }
    return [section.number, section.mass, section.charge, section.electron].some(
      (metric) => metric && typeof metric === "object" && Array.isArray((metric as { dens?: unknown }).dens)
    )
  })
}

export const isLipidOrderAnalysis = (obj: Analysis): obj is LipidOrderAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as LipidOrderAnalysis
  if (!payload.data || typeof payload.data !== "object") return false
  const lipidEntries = Object.values(payload.data)
  if (!lipidEntries.length) return false
  return lipidEntries.some((segments) => {
    if (!segments || typeof segments !== "object") return false
    return Object.values(segments).some((segment) => {
      if (!segment || typeof segment !== "object") return false
      return Array.isArray((segment as { avg?: unknown }).avg)
    })
  })
}

export const isClustersAnalysis = (obj: Analysis): obj is ClustersAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as ClustersAnalysis
  if (!Array.isArray(payload.clusters) || !payload.clusters.length) {
    return false
  }

  const clustersValid = payload.clusters.every((cluster) => {
    if (!cluster || typeof cluster !== "object") return false
    const frames = Array.isArray(cluster.frames) ? cluster.frames : []
    return (
      typeof cluster.main === "number" &&
      Number.isFinite(cluster.main) &&
      frames.every((frame) => typeof frame === "number" && Number.isFinite(frame))
    )
  })

  const transitions = Array.isArray(payload.transitions) ? payload.transitions : []
  const transitionsValid = transitions.every((transition) => {
    if (!transition || typeof transition !== "object") return false
    return (
      typeof transition.from === "number" &&
      Number.isFinite(transition.from) &&
      typeof transition.to === "number" &&
      Number.isFinite(transition.to) &&
      typeof transition.count === "number" &&
      Number.isFinite(transition.count)
    )
  })

  return (
    typeof payload.name === "string" &&
    typeof payload.cutoff === "number" &&
    Number.isFinite(payload.cutoff) &&
    typeof payload.step === "number" &&
    Number.isFinite(payload.step) &&
    typeof payload.version === "string" &&
    clustersValid &&
    transitionsValid
  )
}

const sanitizeEnergyLabelArray = (values: unknown): string[] =>
  Array.isArray(values)
    ? values.map((value) => (typeof value === "string" ? value.trim() : "")).filter((value) => Boolean(value))
    : []

const createEmptyEnergyAgent = (): EnergiesAgentData => ({
  labels: [],
  es: [],
  ies: [],
  fes: [],
  vdw: [],
  ivdw: [],
  fvdw: [],
  both: [],
  iboth: [],
  fboth: [],
})

const hasEnergySeries = (agent: EnergiesAgentData) =>
  agent.es.length ||
  agent.ies.length ||
  agent.fes.length ||
  agent.vdw.length ||
  agent.ivdw.length ||
  agent.fvdw.length ||
  agent.both.length ||
  agent.iboth.length ||
  agent.fboth.length

const normalizeEnergyAgent = (agent: unknown): EnergiesAgentData => {
  if (!agent || typeof agent !== "object") {
    return createEmptyEnergyAgent()
  }

  const payload = agent as Partial<EnergiesAgentData>
  return {
    labels: sanitizeEnergyLabelArray(payload.labels),
    es: sanitizeNumericArray(payload.es),
    ies: sanitizeNumericArray(payload.ies),
    fes: sanitizeNumericArray(payload.fes),
    vdw: sanitizeNumericArray(payload.vdw),
    ivdw: sanitizeNumericArray(payload.ivdw),
    fvdw: sanitizeNumericArray(payload.fvdw),
    both: sanitizeNumericArray(payload.both),
    iboth: sanitizeNumericArray(payload.iboth),
    fboth: sanitizeNumericArray(payload.fboth),
  }
}

const normalizeEnergiesEntry = (entry: unknown, index: number): EnergiesAnalysis["data"][number] | undefined => {
  if (!entry || typeof entry !== "object") return undefined
  const record = entry as {
    name?: unknown
    agent1?: unknown
    agent2?: unknown
  }

  const agent1 = normalizeEnergyAgent(record.agent1)
  const agent2 = normalizeEnergyAgent(record.agent2)

  if (!hasEnergySeries(agent1) && !hasEnergySeries(agent2)) {
    return undefined
  }

  const name =
    typeof record.name === "string" && record.name.trim().length ? record.name.trim() : `Interaction ${index + 1}`

  return {
    name,
    agent1,
    agent2,
  }
}

const hasEnergyAgentData = (agent: unknown): agent is EnergiesAgentData => {
  if (!agent || typeof agent !== "object") return false
  const payload = agent as EnergiesAgentData
  const arrays: Array<unknown> = [
    payload.labels,
    payload.es,
    payload.ies,
    payload.fes,
    payload.vdw,
    payload.ivdw,
    payload.fvdw,
    payload.both,
    payload.iboth,
    payload.fboth,
  ]
  return arrays.every((value) => Array.isArray(value))
}

const isEnergiesAnalysis = (obj: Analysis): obj is EnergiesAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as EnergiesAnalysis
  if (!Array.isArray(payload.data) || !payload.data.length) return false
  return payload.data.every((entry) => {
    if (!entry || typeof entry !== "object") return false
    const record = entry as { agent1?: unknown; agent2?: unknown }
    return hasEnergyAgentData(record.agent1) && hasEnergyAgentData(record.agent2)
  })
}

export const extractEnergiesAnalysis = (obj: Analysis): EnergiesAnalysis | undefined => {
  if (isEnergiesAnalysis(obj)) {
    return obj
  }

  if (!obj || typeof obj !== "object") return undefined

  const payload = obj as { data?: unknown }
  const sources: unknown[] = []

  if (Array.isArray(payload.data) && payload.data.length) {
    sources.push(...payload.data)
  } else if (Array.isArray(obj)) {
    sources.push(...obj)
  } else {
    sources.push(obj)
  }

  const normalized = sources
    .map((entry, index) => normalizeEnergiesEntry(entry, index))
    .filter((entry): entry is EnergiesAnalysis["data"][number] => Boolean(entry))

  if (!normalized.length) return undefined

  return { data: normalized }
}

export const isMembraneMapAnalysis = (obj: Analysis): obj is MembraneMapAnalysis => {
  if (!obj || typeof obj !== "object") return false
  const payload = obj as MembraneMapAnalysis
  const mems = payload.mems
  const entries = mems && typeof mems === "object" ? Object.values(mems) : []
  const hasMembraneEntries = entries.length > 0
  const hasUnassigned = Array.isArray(payload.no_mem_lipid)
  if (!hasMembraneEntries && !hasUnassigned) {
    return false
  }
  if (!hasMembraneEntries) {
    return true
  }
  return entries.every((entry) => {
    if (!entry || typeof entry !== "object") return false
    const leaflets = (entry as { leaflets?: unknown }).leaflets as { top?: unknown; bot?: unknown } | undefined
    const polar = (entry as { polar_atoms?: unknown }).polar_atoms as { top?: unknown; bot?: unknown } | undefined
    return (
      !!leaflets &&
      typeof leaflets === "object" &&
      Array.isArray(leaflets.top) &&
      Array.isArray(leaflets.bot) &&
      !!polar &&
      typeof polar === "object" &&
      Array.isArray(polar.top) &&
      Array.isArray(polar.bot)
    )
  })
}

const isInteractionEntry = (entry: unknown): entry is InteractionData => {
  if (!entry || typeof entry !== "object") return false
  const payload = entry as InteractionData
  return typeof payload.name === "string" || typeof payload.agent_1 === "string" || typeof payload.agent_2 === "string"
}

export const isInteractionsAnalysis = (
  obj: Analysis | InteractionData[]
): obj is InteractionData | InteractionData[] => {
  if (Array.isArray(obj)) {
    return obj.every(isInteractionEntry)
  }
  return isInteractionEntry(obj)
}

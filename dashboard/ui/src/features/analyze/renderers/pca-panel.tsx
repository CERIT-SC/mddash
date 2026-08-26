import type { FC } from "react"
import { useMemo, useState } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@e-infra/design-system"

import type { PCAAnalysis } from "../analysis-types"
import { formatStatValue, Scatter2D, ScreePlot } from "../charts"

type PcaAnalysisPanelProps = {
  data: PCAAnalysis
}

const PcaAnalysisPanel: FC<PcaAnalysisPanelProps> = ({ data }) => {
  const componentCount = Math.max(data.eigenvalues.length, data.projections[0]?.length ?? 0)
  const axisOptions = useMemo(() => Array.from({ length: componentCount }, (_, idx) => idx + 1), [componentCount])

  const [xComponent, setXComponent] = useState<number>(1)
  const [yComponent, setYComponent] = useState<number>(Math.min(2, componentCount) || 1)

  const variancePercents = useMemo(() => {
    const total = data.eigenvalues.reduce((sum, val) => sum + val, 0) || 1
    return data.eigenvalues.map((val) => (val / total) * 100)
  }, [data.eigenvalues])

  const scatterPoints = useMemo(
    () =>
      data.projections.map((projection, index) => ({
        x: projection[xComponent - 1] ?? 0,
        y: projection[yComponent - 1] ?? 0,
        c: index,
      })),
    [data.projections, xComponent, yComponent]
  )

  const xLabel = `PC${xComponent} (${formatStatValue(variancePercents[xComponent - 1] ?? 0, 1)}%)`
  const yLabel = `PC${yComponent} (${formatStatValue(variancePercents[yComponent - 1] ?? 0, 1)}%)`

  const hasScatter = componentCount >= 2

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="border-border flex min-h-0 flex-col rounded-lg border p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Explained variance</p>
              <p className="text-text-muted text-xs">Scree plot of principal component eigenvalues</p>
            </div>
            <p className="text-text-muted text-xs">
              Top PC captures {formatStatValue(variancePercents[0] ?? 0, 1)}% of the variance
            </p>
          </div>
          <div className="min-h-55 flex-1">
            <ScreePlot eigenvalues={data.eigenvalues} />
          </div>
        </div>

        <div className="border-border flex min-h-0 flex-col rounded-lg border p-4">
          <div className="mb-4 flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">X-axis:</span>
              <Select value={String(xComponent)} onValueChange={(value) => setXComponent(Number(value))}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {axisOptions.map((option) => (
                    <SelectItem key={`x-${option}`} value={String(option)}>
                      PC {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {hasScatter && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Y-axis:</span>
                <Select value={String(yComponent)} onValueChange={(value) => setYComponent(Number(value))}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {axisOptions.map((option) => (
                      <SelectItem key={`y-${option}`} value={String(option)}>
                        PC {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="min-h-70 flex-1">
            {hasScatter ? (
              <Scatter2D points={scatterPoints} xLabel={xLabel} yLabel={yLabel} />
            ) : (
              <div className="text-text-muted flex h-full items-center justify-center text-center text-sm">
                PCA projections need at least two components to show a scatter plot.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default PcaAnalysisPanel

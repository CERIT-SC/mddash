import { useCallback, useMemo, useState } from "react"

import { Loader2, Star } from "lucide-react"

import { statusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import { getJobStatusVariant, type JobStatus, type TunerTrial } from "@/util/types"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import ConfirmDialog from "@/components/ConfirmDialog"

interface TunerTableProps {
  rows: TunerTrial[]
  selectedTrial: TunerTrial | null
  setSelectedTrial: (trial: TunerTrial | null) => void
  tunerStopped?: boolean
}

const TunerTable = (props: TunerTableProps) => {
  const { rows, selectedTrial, setSelectedTrial, tunerStopped = false } = props

  const [confirmChoiceDialog, setConfirmChoiceDialog] = useState(false)

  const sortedRows = useMemo(() => {
    const statusRank: Record<JobStatus, number> = {
      TERMINATED: 0,
      RUNNING: 1,
      ERROR: 2,
      PENDING: 3,
      UNKNOWN: 4,
    }

    return [...rows].sort((a, b) => {
      if (a.performance === null && b.performance === null) return statusRank[a.status] - statusRank[b.status]
      if (a.performance === null) return 1
      if (b.performance === null) return -1
      if (a.performance !== b.performance) return b.performance - a.performance
      return statusRank[a.status] - statusRank[b.status]
    })
  }, [rows])

  const handleRadioClick = useCallback(
    (row: TunerTrial, isOptimal: boolean) => {
      if (selectedTrial?.id === row.id) {
        setSelectedTrial(null)
        return
      }
      if (!isOptimal) setConfirmChoiceDialog(true)
      setSelectedTrial(row)
    },
    [selectedTrial, setSelectedTrial]
  )

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-md border p-6">
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          {tunerStopped ? (
            <span>No trials completed. The tuning job was stopped before any trials finished.</span>
          ) : (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Waiting for tuning trials...</span>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            <TableRow className="bg-primary hover:bg-primary">
              <TableHead className="text-primary-foreground text-center">Select</TableHead>
              <TableHead className="text-primary-foreground">Status</TableHead>
              <TableHead className="text-primary-foreground text-right">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">Performance</span>
                  </TooltipTrigger>
                  <TooltipContent>Measured performance (ns/day)</TooltipContent>
                </Tooltip>
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">PME</span>
                  </TooltipTrigger>
                  <TooltipContent>Device type for PME calculations</TooltipContent>
                </Tooltip>
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">NB</span>
                  </TooltipTrigger>
                  <TooltipContent>Device type for non-bonded interactions</TooltipContent>
                </Tooltip>
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">NP</span>
                  </TooltipTrigger>
                  <TooltipContent>Number of MPI processes</TooltipContent>
                </Tooltip>
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">NTOMP</span>
                  </TooltipTrigger>
                  <TooltipContent>Number of OpenMP threads per MPI rank</TooltipContent>
                </Tooltip>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedRows.map((row, idx) => {
              const isOptimal = idx === 0 && row.performance !== null
              const variant = getJobStatusVariant(row.status as JobStatus)
              return (
                <TableRow key={row.id} className={cn(isOptimal && "bg-primary/5 dark:bg-primary/10")}>
                  <TableCell className="relative">
                    <div className="flex items-center justify-center">
                      <input
                        type="radio"
                        name="selectedTrial"
                        checked={selectedTrial?.id === row.id}
                        onChange={() => handleRadioClick(row, isOptimal)}
                        onClick={() => {
                          if (selectedTrial?.id === row.id) {
                            setSelectedTrial(null)
                          }
                        }}
                        className={"accent-primary cursor-pointer"}
                      />
                    </div>
                    {isOptimal && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Star className="absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 cursor-default fill-yellow-400 text-yellow-400" />
                        </TooltipTrigger>
                        <TooltipContent>Best performing trial</TooltipContent>
                      </Tooltip>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn("text-xs", statusBadgeClass(variant))}>
                      {row.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {row.performance !== null ? row.performance.toFixed(2) : "N/A"}
                  </TableCell>
                  <TableCell className="text-right">{row.pme}</TableCell>
                  <TableCell className="text-right">{row.nb}</TableCell>
                  <TableCell className="text-right">{row.np}</TableCell>
                  <TableCell className="text-right">{row.ntomp}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
      <ConfirmDialog
        open={confirmChoiceDialog}
        setOpen={setConfirmChoiceDialog}
        onCancel={() => setSelectedTrial(null)}
        message="The selected trial doesn't have the optimal performance. Are you sure you want to proceed with these parameters?"
        confirmColor="warning"
      />
    </>
  )
}

export default TunerTable

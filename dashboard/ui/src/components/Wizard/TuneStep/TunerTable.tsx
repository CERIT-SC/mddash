import { useCallback, useMemo, useState } from "react"

import { Loader2, Star, Terminal } from "lucide-react"

import { statusBadgeClass } from "@/lib/status"
import { cn } from "@/lib/utils"
import { formatEstimatedCost, formatEstimatedTime } from "@/util/estimate-format"
import { getTunerJobStatusVariant, tunerTrialRank, type GmxTunerTrial as TunerTrial } from "@/util/types"
import { useTunerTrialLogs } from "@/hooks/use-tuner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import ConfirmDialog from "@/components/ConfirmDialog"
import LogsView from "@/components/LogsView"

interface TunerTableProps {
  rows: TunerTrial[]
  selectedTrial: TunerTrial | null
  setSelectedTrial: (trial: TunerTrial | null) => void
  tunerStopped?: boolean
  experimentId: string
  simulationPath: string
}

const TunerTable = (props: TunerTableProps) => {
  const { rows, selectedTrial, setSelectedTrial, tunerStopped = false, experimentId, simulationPath } = props

  const [confirmChoiceDialog, setConfirmChoiceDialog] = useState(false)
  const [logsTrialId, setLogsTrialId] = useState<string | null>(null)

  const { stdout, stderr } = useTunerTrialLogs(experimentId, simulationPath, logsTrialId)

  const sortedRows = useMemo(() => {
    return [...rows].sort((a: TunerTrial, b: TunerTrial) => {
      if (a.performance === null && b.performance === null) return tunerTrialRank(a.status) - tunerTrialRank(b.status)
      if (a.performance === null) return 1
      if (b.performance === null) return -1
      if (a.performance !== b.performance) return b.performance - a.performance
      return tunerTrialRank(a.status) - tunerTrialRank(b.status)
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
                    <span className="cursor-help">Est. Time</span>
                  </TooltipTrigger>
                  <TooltipContent>Estimated time to run the full simulation with this configuration</TooltipContent>
                </Tooltip>
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="cursor-help">Est. Cost</span>
                  </TooltipTrigger>
                  <TooltipContent>Estimated cost of the full simulation, from hourly CPU/GPU/RAM rates</TooltipContent>
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
              const variant = getTunerJobStatusVariant(row.status)
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
                    <div className="flex items-center gap-1.5">
                      <Badge variant="outline" className={cn("text-xs", statusBadgeClass(variant))}>
                        {row.status}
                      </Badge>
                      {row.status === "ERROR" && !tunerStopped && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-muted-foreground hover:text-foreground h-5 w-5"
                              onClick={() => setLogsTrialId(row.id)}
                            >
                              <Terminal className="h-3.5 w-3.5" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>View trial logs</TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    {row.performance !== null ? row.performance.toFixed(2) : "N/A"}
                  </TableCell>
                  <TableCell className="text-right">{formatEstimatedTime(row.estimated_time)}</TableCell>
                  <TableCell className="text-right">{formatEstimatedCost(row.estimated_cost)}</TableCell>
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
      <Dialog open={logsTrialId !== null} onOpenChange={(open) => !open && setLogsTrialId(null)}>
        <DialogContent className="sm:max-w-[50vw]">
          <DialogHeader>
            <DialogTitle>Trial Logs — Trial {logsTrialId}</DialogTitle>
          </DialogHeader>
          <Tabs defaultValue="stdout">
            <TabsList>
              <TabsTrigger value="stdout">stdout</TabsTrigger>
              <TabsTrigger value="stderr">stderr</TabsTrigger>
            </TabsList>
            <TabsContent value="stdout">
              <LogsView logs={stdout.data ?? ""} isLoading={stdout.isLoading} />
            </TabsContent>
            <TabsContent value="stderr">
              <LogsView logs={stderr.data ?? ""} isLoading={stderr.isLoading} />
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

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

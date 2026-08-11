import { useCallback, useEffect, useMemo, useState } from "react"

import { Loader2, Terminal } from "lucide-react"

import { computeTrialClasses } from "@/lib/trial-classes"
import { formatCost, formatDuration } from "@/util/helpers"
import { type JobStatus, type GmxTunerTrial as TunerTrial } from "@/util/types"
import { useTunerTrialLogs } from "@/hooks/use-tuner"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import ConfirmDialog from "@/components/ConfirmDialog"
import { JobStatusChip } from "@/components/JobStatusChip"
import LogsView from "@/components/LogsView"
import { TableHeadHelp } from "@/components/TableHeadHelp"
import { TrialClassBadges } from "@/components/TrialClassBadges"

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

  const visibleRows = rows

  const sortedRows = useMemo(() => {
    const statusRank: Record<JobStatus, number> = {
      FINISHED: 0,
      RUNNING: 1,
      ERROR: 2,
      PENDING: 3,
      UNKNOWN: 4,
    }

    return [...visibleRows].sort((a: TunerTrial, b: TunerTrial) => {
      if (a.performance === null && b.performance === null) return statusRank[a.status] - statusRank[b.status]
      if (a.performance === null) return 1
      if (b.performance === null) return -1
      if (a.performance !== b.performance) return b.performance - a.performance
      return statusRank[a.status] - statusRank[b.status]
    })
  }, [visibleRows])

  const trialClasses = useMemo(() => computeTrialClasses(visibleRows), [visibleRows])

  // A selected trial that becomes hidden (pruned on completion) must not stay active.
  useEffect(() => {
    if (selectedTrial && !visibleRows.some((r) => r.id === selectedTrial.id)) setSelectedTrial(null)
  }, [selectedTrial, visibleRows, setSelectedTrial])

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

  if (visibleRows.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-md border p-6">
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          {tunerStopped ? (
            <span>No trials have produced a performance measurement.</span>
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
              <TableHead className="text-primary-foreground" />
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp label="Performance" description="Measured performance (ns/day)" />
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp
                  label="Est. Time"
                  description="Estimated time to run the full simulation with this configuration"
                />
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp
                  label="Est. Cost"
                  description="Estimated cost of the full simulation, from hourly CPU/GPU/RAM rates"
                />
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp label="PME" description="Device type for PME calculations" />
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp label="NB" description="Device type for non-bonded interactions" />
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp label="NP" description="Number of MPI processes" />
              </TableHead>
              <TableHead className="text-primary-foreground text-right">
                <TableHeadHelp label="NTOMP" description="Number of OpenMP threads per MPI rank" />
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedRows.map((row, idx) => {
              const isOptimal = idx === 0 && row.performance !== null
              return (
                <TableRow key={row.id}>
                  <TableCell>
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
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <JobStatusChip status={row.status as JobStatus} />
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
                  <TableCell>
                    <TrialClassBadges classes={trialClasses.get(row.id)} />
                  </TableCell>
                  <TableCell className="text-right">
                    {row.performance !== null ? row.performance.toFixed(2) : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {row.estimated_time === null ? "—" : formatDuration(row.estimated_time * 3600)}
                  </TableCell>
                  <TableCell className="text-right">{formatCost(row.estimated_cost)}</TableCell>
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

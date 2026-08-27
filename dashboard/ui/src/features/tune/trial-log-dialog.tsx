import { useState } from "react"

import { useGetTunerTrialStderr, useGetTunerTrialStdout } from "@/api/generated/client"
import { LogPane } from "@/shared/ui/log-pane"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@e-infra/design-system"

type TrialLogDialogProps = {
  experimentId: string
  simulationPath: string
  trialId: string | null
  onClose: () => void
}

/** stdout/stderr for one trial, mainly for diagnosing failed configurations. */
export function TrialLogDialog({ experimentId, simulationPath, trialId, onClose }: TrialLogDialogProps) {
  const open = trialId !== null
  const [tab, setTab] = useState<"stdout" | "stderr">("stdout")
  // Only the visible stream is fetched.
  const stdout = useGetTunerTrialStdout(experimentId, simulationPath, trialId ?? "", {
    query: { enabled: open && tab === "stdout", retry: false },
  })
  const stderr = useGetTunerTrialStderr(experimentId, simulationPath, trialId ?? "", {
    query: { enabled: open && tab === "stderr", retry: false },
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {/* minmax fixes the DS grid auto-track blowing out on long unbreakable log lines */}
      <DialogContent className="grid-cols-[minmax(0,1fr)] sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Trial output</DialogTitle>
          <DialogDescription>Logs reported by the tuner for this trial.</DialogDescription>
        </DialogHeader>
        {/* key remounts the tabs on stdout when the trial changes */}
        <Tabs key={trialId} value={tab} onValueChange={(next) => setTab(next as "stdout" | "stderr")}>
          <TabsList aria-label="Log stream">
            <TabsTrigger value="stdout">Standard output</TabsTrigger>
            <TabsTrigger value="stderr">Standard error</TabsTrigger>
          </TabsList>
          {(
            [
              ["stdout", "Standard output", stdout],
              ["stderr", "Standard error", stderr],
            ] as const
          ).map(([stream, label, query]) => (
            <TabsContent key={stream} value={stream} className="pt-3">
              <LogPane
                isLoading={query.isPending}
                errorText={query.isError ? "The log could not be loaded." : undefined}
                logs={query.data?.status === 200 ? query.data.data : undefined}
                emptyText={`${label} is empty.`}
              />
            </TabsContent>
          ))}
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

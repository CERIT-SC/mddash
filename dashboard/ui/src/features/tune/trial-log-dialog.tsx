import { useState } from "react"

import { useGetTunerTrialStderr, useGetTunerTrialStdout } from "@/api/generated/client"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Skeleton,
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

type LogPaneProps = {
  pending: boolean
  error: boolean
  text: string | undefined
  emptyLabel: string
}

function LogPane({ pending, error, text, emptyLabel }: LogPaneProps) {
  if (pending) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    )
  }
  if (error) {
    return <p className="text-text-muted text-sm">The log could not be loaded.</p>
  }
  if (text === undefined || text.trim() === "") {
    return <p className="text-text-muted text-sm">{emptyLabel}</p>
  }
  return (
    <pre className="bg-surface text-text max-h-96 overflow-auto rounded-md p-3 font-mono text-xs break-all whitespace-pre-wrap">
      {text}
    </pre>
  )
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
                pending={query.isPending}
                error={query.isError}
                text={query.data?.status === 200 ? query.data.data : undefined}
                emptyLabel={`${label} is empty.`}
              />
            </TabsContent>
          ))}
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

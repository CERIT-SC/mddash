import { cn } from "@/lib/utils"

export interface LogsViewProps {
  logs: string
  className?: string
}

export default function LogsView({ logs, className }: LogsViewProps) {
  return (
    <div
      className={cn("h-96 w-full overflow-auto rounded-md border p-3 font-mono text-sm whitespace-pre-wrap", className)}
      ref={(el) => el?.scrollTo(0, el.scrollHeight)}
    >
      {logs || "Loading..."}
    </div>
  )
}

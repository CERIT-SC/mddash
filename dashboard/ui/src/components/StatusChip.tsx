import { Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"

type StatusChipProps = {
  label: string
  statusClassName: string
  active?: boolean
  className?: string
}

export function StatusChip({ label, statusClassName, active = false, className }: StatusChipProps) {
  return (
    <Badge variant="outline" className={cn("text-xs", statusClassName, className)}>
      {active && <Loader2 className="animate-spin" />}
      {label}
    </Badge>
  )
}

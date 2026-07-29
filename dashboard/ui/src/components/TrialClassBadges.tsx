import { CircleDollarSign, Leaf, Zap, type LucideIcon } from "lucide-react"

import type { TrialClass } from "@/lib/trial-classes"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

type Props = {
  classes?: TrialClass[]
  className?: string
}

const CLASS_META: Record<TrialClass, { icon: LucideIcon; label: string; tooltip: string; badgeClass: string }> = {
  fastest: {
    icon: Zap,
    label: "Fastest",
    tooltip: "Highest measured performance of all finished trials",
    badgeClass: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  },
  "most-efficient": {
    icon: Leaf,
    label: "Most efficient",
    tooltip: "Cheapest full production run of all finished trials",
    badgeClass: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  },
  "most-expensive": {
    icon: CircleDollarSign,
    label: "Most expensive",
    tooltip: "Highest full-run cost of all finished trials — expensive to run",
    badgeClass: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  },
}

export function TrialClassBadges({ classes, className }: Props) {
  if (!classes?.length) return <span className="text-muted-foreground text-xs">—</span>
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {classes.map((cls) => {
        const meta = CLASS_META[cls]
        const Icon = meta.icon
        return (
          <Tooltip key={cls}>
            <TooltipTrigger asChild>
              <Badge className={cn("cursor-default text-xs", meta.badgeClass)}>
                <Icon />
                {meta.label}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>{meta.tooltip}</TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}

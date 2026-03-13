import { useId, useState } from "react"

import { ChevronDown, ChevronUp, SlashIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

type LabeledListProps = {
  label: string
  list: string[]
  orientation?: "horizontal" | "vertical"
  className?: string
  maxVisibleItems?: number
}

const LabeledList = ({ label, list, orientation = "horizontal", className, maxVisibleItems = 5 }: LabeledListProps) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const contentId = useId()

  const isHorizontal = orientation === "horizontal"
  const shouldCollapse = list.length > maxVisibleItems

  const visibleItems = shouldCollapse && !isExpanded ? list.slice(0, maxVisibleItems) : list

  const toggleIsExpanded = () => {
    setIsExpanded((prev) => !prev)
  }

  return (
    <div
      className={cn(
        "flex gap-2.5",
        isHorizontal ? "items-center" : "flex-col items-start gap-[5px]",
        isExpanded && "items-start",
        className
      )}
    >
      <p className={cn("shrink-0", !isHorizontal && "text-sm font-semibold")}>
        {label}
        {isHorizontal && ":"}
      </p>

      <div className="flex items-center gap-2.5">
        <div id={contentId} className="flex flex-wrap items-center gap-1">
          {visibleItems.map((item, index) => (
            <span key={item} className="flex items-center gap-1">
              <span className="text-muted-foreground text-sm break-all">{item}</span>

              {index < list.length - 1 &&
                (isExpanded || index < visibleItems.length - 1 ? (
                  <SlashIcon className="text-muted-foreground h-3 w-3" />
                ) : null)}
            </span>
          ))}

          {shouldCollapse && !isExpanded && <span className="text-muted-foreground text-sm">...</span>}
        </div>

        {shouldCollapse && (
          <Button
            onClick={toggleIsExpanded}
            variant="ghost"
            size="icon"
            className="size-6 shrink-0 self-start p-0"
            aria-expanded={isExpanded}
            aria-controls={contentId}
            aria-label={isExpanded ? `Collapse ${label} list` : `Show all ${label}`}
          >
            {isExpanded ? (
              <ChevronUp className="text-muted-foreground h-5 w-5 shrink-0" />
            ) : (
              <ChevronDown className="text-muted-foreground h-5 w-5 shrink-0" />
            )}
          </Button>
        )}
      </div>
    </div>
  )
}

export default LabeledList

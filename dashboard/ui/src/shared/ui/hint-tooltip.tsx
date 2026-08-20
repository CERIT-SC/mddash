import { Tooltip, TooltipContent, TooltipTrigger } from "@e-infra/design-system"
import { CircleHelp } from "lucide-react"

type HintTooltipProps = {
  text: string
}

/** Small circled-question tooltip trigger used for field labels and column headers. */
export function HintTooltip({ text }: HintTooltipProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={text}
          className="text-text-muted hover:text-text inline-flex cursor-help items-center align-middle"
        >
          <CircleHelp className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  )
}

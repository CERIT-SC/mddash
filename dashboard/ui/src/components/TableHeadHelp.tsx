import { CircleQuestionMark } from "lucide-react"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

type Props = {
  label: string
  description: string
}

export function TableHeadHelp({ label, description }: Props) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="inline-flex cursor-help items-center gap-1">
          {label}
          <CircleQuestionMark className="size-3.5 opacity-75" aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{description}</TooltipContent>
    </Tooltip>
  )
}

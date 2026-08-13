import type { ReactNode } from "react"

import { CardDescription, CardHeader, CardTitle } from "@e-infra/design-system"
import type { LucideIcon } from "lucide-react"

type IconTone = "primary" | "success" | "warning" | "error"

const TONE_CLASSES: Record<IconTone, string> = {
  primary: "text-primary",
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
}

/** Card header with a colored icon before the title — used by every hub card page. */
export function IconCardHeader({
  icon: Icon,
  tone = "primary",
  title,
  description,
}: {
  icon: LucideIcon
  tone?: IconTone
  title: ReactNode
  description?: ReactNode
}) {
  return (
    <CardHeader>
      <CardTitle className="flex items-center gap-2">
        <Icon className={TONE_CLASSES[tone]} size={20} aria-hidden="true" />
        {title}
      </CardTitle>
      {description ? <CardDescription>{description}</CardDescription> : null}
    </CardHeader>
  )
}

import type { ComponentProps } from "react"

import { Alert, cn } from "@e-infra/design-system"

export function InfoBanner({ className, ...props }: ComponentProps<typeof Alert>) {
  return <Alert className={cn("border-info-600 bg-info-200 border-l-8", className)} {...props} />
}

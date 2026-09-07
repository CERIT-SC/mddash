import type { ComponentProps } from "react"

import { Alert, cn } from "@e-infra/design-system"

export function InfoBanner({ className, ...props }: ComponentProps<typeof Alert>) {
  return <Alert className={cn("bg-info-200", className)} {...props} />
}

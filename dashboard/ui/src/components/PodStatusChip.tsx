import { isActivePodStatus, podStatusBadgeClass } from "@/lib/status"
import type { PodStatus } from "@/util/types"
import { StatusChip } from "@/components/StatusChip"

type PodStatusChipProps = {
  status: PodStatus
  className?: string
}

export function PodStatusChip({ status, className }: PodStatusChipProps) {
  return (
    <StatusChip
      label={status}
      active={isActivePodStatus(status)}
      statusClassName={podStatusBadgeClass(status)}
      className={className}
    />
  )
}

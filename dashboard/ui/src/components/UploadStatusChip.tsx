import { isActiveUploadState, uploadStatusBadgeClass } from "@/lib/status"
import type { UploadState } from "@/util/types"
import { StatusChip } from "@/components/StatusChip"

type UploadStatusChipProps = {
  status: UploadState
  className?: string
}

export function UploadStatusChip({ status, className }: UploadStatusChipProps) {
  return (
    <StatusChip
      label={status.toUpperCase()}
      active={isActiveUploadState(status)}
      statusClassName={uploadStatusBadgeClass(status)}
      className={className}
    />
  )
}

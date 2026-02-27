import type { StatusVariant } from "@/util/types"

export function statusBadgeClass(variant: StatusVariant): string {
  switch (variant) {
    case "success":
      return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
    case "warning":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
    case "info":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
    case "destructive":
      return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
    case "secondary":
      return "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
    default:
      return ""
  }
}

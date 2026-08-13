import type { Problem } from "@/api/generated/models"

export class ApiError extends Error {
  readonly title: string
  readonly type?: string
  readonly status?: number

  constructor(title: string, message: string, options?: { type?: string; status?: number }) {
    super(message)
    this.name = "ApiError"
    this.title = title
    this.type = options?.type
    this.status = options?.status
  }
}

function isProblem(value: unknown): value is Problem {
  if (typeof value !== "object" || value === null) return false
  const problem = value as Record<string, unknown>
  return typeof problem.title === "string" && typeof problem.detail === "string"
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (typeof error === "object" && error !== null && "info" in error) {
    const generated = error as { info: unknown; status?: number }
    if (isProblem(generated.info)) {
      return new ApiError(generated.info.title, generated.info.solution ?? generated.info.detail, {
        type: generated.info.type,
        status: generated.status,
      })
    }
  }
  if (error instanceof TypeError) {
    return new ApiError("Network unavailable", "Check your connection and retry.")
  }
  return new ApiError("Unexpected error", "Retry the action or contact support.")
}

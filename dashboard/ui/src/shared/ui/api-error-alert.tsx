import { toApiError } from "@/api/errors"
import { Alert, AlertDescription, AlertTitle, Button } from "@e-infra/design-system"

type ApiErrorAlertProps = {
  error: unknown
  onRetry?: () => void
}

export function ApiErrorAlert({ error, onRetry }: ApiErrorAlertProps) {
  const apiError = toApiError(error)
  return (
    <Alert role="alert" variant="error">
      <AlertTitle>{apiError.title}</AlertTitle>
      <AlertDescription>
        <p>{apiError.message}</p>
        {apiError.type ? <p className="text-text-muted text-xs">Support ID: {apiError.type}</p> : null}
        {onRetry ? (
          <Button className="mt-4" size="sm" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}

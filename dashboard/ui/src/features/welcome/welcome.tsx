import { toApiError } from "@/api/errors"
import { useListExperiments } from "@/api/generated/client"
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  H1,
  P,
} from "@e-infra/design-system"

type WelcomeProps = { user: string }

export function Welcome({ user }: WelcomeProps) {
  const query = useListExperiments({ query: { retry: false } })
  const response = query.data
  const error = query.isError ? toApiError(query.error) : undefined

  let countLabel = "Loading experiment count"
  if (response?.status === 200) {
    const count = response.data.length
    countLabel = count === 0 ? "No experiments yet" : `${count} experiment${count === 1 ? "" : "s"}`
  }

  return (
    <section className="space-y-6 md:space-y-8 lg:space-y-10">
      <div className="space-y-2 md:space-y-3">
        <H1>Welcome, {user}</H1>
        <P className="text-text-muted">Your molecular dynamics workspace is ready.</P>
      </div>
      <Card className="bg-surface max-w-md">
        <CardHeader>
          <CardTitle>Experiments</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert role="alert" variant="error">
              <AlertTitle>{error.title}</AlertTitle>
              <AlertDescription>
                <p>{error.message}</p>
                {error.type ? <p className="text-text-muted text-xs">Support ID: {error.type}</p> : null}
                <Button className="mt-4" size="sm" onClick={() => void query.refetch()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : (
            <P aria-live="polite">{countLabel}</P>
          )}
        </CardContent>
      </Card>
    </section>
  )
}

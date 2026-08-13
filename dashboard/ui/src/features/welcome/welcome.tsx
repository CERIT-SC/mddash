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
  const failed = response !== undefined && response.status !== 200

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
          {query.isError ? (
            <Alert role="alert" variant="error">
              <AlertTitle>Experiment count unavailable</AlertTitle>
              <AlertDescription>
                <p>Please retry. If the problem continues, contact support.</p>
                <Button className="mt-4" size="sm" onClick={() => void query.refetch()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : failed ? (
            <Alert role="alert" variant="error">
              <AlertTitle>{response.data.title}</AlertTitle>
              <AlertDescription>
                <p>{response.data.solution ?? response.data.detail}</p>
                <p className="text-text-muted text-xs">Support ID: {response.data.type}</p>
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

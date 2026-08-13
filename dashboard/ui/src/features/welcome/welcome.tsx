import { useListExperiments } from "@/api/generated/client"
import { ApiErrorAlert } from "@/shared/ui/api-error-alert"
import { Card, CardContent, CardHeader, CardTitle, H1, P } from "@e-infra/design-system"

type WelcomeProps = { user: string }

export function Welcome({ user }: WelcomeProps) {
  const query = useListExperiments({ query: { retry: false } })
  const response = query.data

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
            <ApiErrorAlert error={query.error} onRetry={() => void query.refetch()} />
          ) : (
            <P aria-live="polite">{countLabel}</P>
          )}
        </CardContent>
      </Card>
    </section>
  )
}

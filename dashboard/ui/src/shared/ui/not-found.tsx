import { H1, P } from "@e-infra/design-system"

export function NotFound() {
  return (
    <section className="space-y-2 md:space-y-3">
      <H1>Page not found</H1>
      <P className="text-text-muted">The requested dashboard page does not exist.</P>
    </section>
  )
}

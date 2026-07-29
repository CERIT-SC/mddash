import { Alert } from "@e-infra/design-system"

/**
 * Hub-configured announcements arrive as raw HTML from the operator
 * (same rendering promise the stock page.html template makes).
 */
export function Announcement({ html }: { html?: string | null }) {
  if (!html) return null
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-4">
      <Alert variant="warning" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  )
}

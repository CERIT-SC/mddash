import { useEffect } from "react"

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, P } from "@e-infra/design-system"
import { Home, TriangleAlert } from "lucide-react"

import { CenteredLayout } from "../components/Layouts"
import { getAppConfig } from "../lib/config"

interface ErrorConfig {
  statusCode: number
  statusMessage: string
  message: string | null
  messageHtml: string | null
  extraErrorHtml: string | null
}

/** Shared by error.html and 404.html (the 404 entry only changes the defaults). */
export function ErrorPage({ notFound = false }: { notFound?: boolean }) {
  const cfg = getAppConfig<ErrorConfig>({
    statusCode: notFound ? 404 : 500,
    statusMessage: notFound ? "Not Found" : "Internal Server Error",
    message: notFound ? "Jupyter has lots of moons, but this is not one..." : null,
    messageHtml: null,
    extraErrorHtml: null,
  })

  // Strip the hub's redirect-loop counter from the URL.
  useEffect(() => {
    if (window.location.search.length <= 1) return
    const params = window.location.search.slice(1).split("&")
    const index = params.findIndex((p) => p.split("=")[0] === "redirects")
    if (index === -1) return
    params.splice(index, 1)
    const search = params.length ? `?${params.join("&")}` : ""
    window.history.replaceState(
      {},
      "",
      window.location.origin + window.location.pathname + search + window.location.hash
    )
  }, [])

  const friendlyTitle = (() => {
    switch (cfg.statusCode) {
      case 403:
        return "Access denied"
      case 404:
        return "Page not found"
      case 500:
        return "Server error"
      case 502:
        return "Server error"
      case 503:
        return "Service unavailable"
      default:
        return cfg.statusMessage || "Something went wrong"
    }
  })()

  return (
    <CenteredLayout announcement={cfg.announcement}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TriangleAlert className="text-warning" size={20} />
            {friendlyTitle}
          </CardTitle>
          <CardDescription>
            {cfg.statusCode} {cfg.statusMessage}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {cfg.messageHtml ? (
            <P dangerouslySetInnerHTML={{ __html: cfg.messageHtml }} />
          ) : cfg.message ? (
            <P>{cfg.message}</P>
          ) : null}
          {cfg.extraErrorHtml ? <P dangerouslySetInnerHTML={{ __html: cfg.extraErrorHtml }} /> : null}
          <Button className="w-full" asChild>
            <a href={`${cfg.baseUrl}home`} className="no-underline">
              <Home size={16} />
              Back to home
            </a>
          </Button>
        </CardContent>
      </Card>
    </CenteredLayout>
  )
}

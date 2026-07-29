import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Checkbox,
  P,
  Small,
} from "@e-infra/design-system"
import { ShieldCheck } from "lucide-react"

import { CenteredLayout } from "../components/Layouts"
import { getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

interface ScopeDescription {
  description: string
  filter?: string
  scope?: string
}

interface OAuthConfig {
  clientDescription: string
  redirectUri: string
  allowedScopes: string[]
  scopeDescriptions: ScopeDescription[]
}

/**
 * OAuth consent page. This MUST be a plain HTML form POST to the same URL —
 * the hub's OAuth handler consumes the form data and completes the redirect.
 */
export function OAuthPage() {
  const cfg = getAppConfig<OAuthConfig>({
    clientDescription: "A Jupyter service",
    redirectUri: "",
    allowedScopes: [],
    scopeDescriptions: [{ description: "Identify you (inherit access to JupyterHub)", scope: "" }],
  })

  return (
    <CenteredLayout maxWidth="max-w-xl">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-center gap-2">
            <ShieldCheck className="text-primary" size={20} />
            Authorize access
          </CardTitle>
          <CardDescription>
            An application is requesting authorization to access data associated with your JupyterHub account.
          </CardDescription>
        </CardHeader>
        <form method="post" action="">
          <CardContent className="flex flex-col gap-4">
            <P className="text-sm">
              {cfg.clientDescription}
              {cfg.redirectUri ? ` (oauth URL: ${cfg.redirectUri})` : ""} would like permission to identify you.
              {cfg.scopeDescriptions.length === 1 && !cfg.scopeDescriptions[0].scope
                ? " It will not be able to take actions on your behalf."
                : ""}
            </P>
            {/* The hidden inputs below are the values the OAuth handler consumes. */}
            <input type="hidden" name="_xsrf" value={cfg.xsrf} />
            {cfg.allowedScopes.map((scope) => (
              <input key={scope} type="hidden" name="scopes" value={scope} />
            ))}
            <Card variant="secondary">
              <CardHeader>
                <CardTitle className="text-base">This will grant the application permission to:</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {cfg.scopeDescriptions.map((scope, i) => (
                  <label key={i} className="flex items-start gap-2 text-sm">
                    {/* Disabled because the authorization is required (STOCK behavior). */}
                    <Checkbox checked disabled title="This authorization is required" />
                    <span>
                      {scope.description}
                      {scope.filter ? <Small className="text-text-muted"> Applies to {scope.filter}.</Small> : null}
                    </span>
                  </label>
                ))}
              </CardContent>
            </Card>
          </CardContent>
          <CardFooter>
            <Button type="submit" size="lg" className="w-full">
              Authorize
            </Button>
          </CardFooter>
        </form>
      </Card>
    </CenteredLayout>
  )
}

mount(<OAuthPage />)

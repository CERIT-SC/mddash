import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Small,
} from "@e-infra/design-system"
import { KeyRound, TriangleAlert } from "lucide-react"

import { CenteredLayout } from "../components/Layouts"
import { DEV_FALLBACK_BASE_URL, getAppConfig } from "../lib/config"
import { mount } from "../lib/mount"

interface LoginConfig {
  loginService: string
  loginUrl: string
  loginError: string | null
  /** Raw HTML override provided by the authenticator (empty when unused). */
  customHtml: string
}

export function LoginPage() {
  const cfg = getAppConfig<LoginConfig>({
    loginService: "e-INFRA CZ",
    loginUrl: `${DEV_FALLBACK_BASE_URL}oauth_login`,
    loginError: null,
    customHtml: "",
  })

  return (
    <CenteredLayout announcement={cfg.announcement}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="text-primary" size={20} />
            Sign in
          </CardTitle>
          <CardDescription>Access your MDDash workspace</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {!window.isSecureContext ? (
            <Alert variant="warning">
              <AlertTitle className="flex items-center gap-2">
                <TriangleAlert size={16} />
                Unsecured connection
              </AlertTitle>
              <AlertDescription>
                JupyterHub seems to be served over an unsecured HTTP connection. We strongly recommend enabling HTTPS.
              </AlertDescription>
            </Alert>
          ) : null}
          {cfg.loginError ? <Alert variant="error">{cfg.loginError}</Alert> : null}
          {cfg.customHtml ? (
            // Raw HTML is provided by the configured authenticator (same
            // rendering contract as the stock login.html template).
            <div dangerouslySetInnerHTML={{ __html: cfg.customHtml }} />
          ) : (
            <Button size="lg" className="w-full" asChild>
              <a href={cfg.loginUrl} className="no-underline">
                Sign in with {cfg.loginService}
              </a>
            </Button>
          )}
          <Small className="text-text-muted">You will be redirected to {cfg.loginService} to sign in.</Small>
        </CardContent>
      </Card>
    </CenteredLayout>
  )
}

mount(<LoginPage />)

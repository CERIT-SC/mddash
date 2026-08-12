import { useCallback, useEffect, useMemo, useState } from "react"

import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  AlertTitle,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  P,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Small,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@e-infra/design-system"
import { Check, Copy, KeyRound, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { AuthedLayout, PageBody } from "../components/Layouts"
import { HubApi, type HubTokenModel } from "../lib/api"
import { getAppConfig } from "../lib/config"
import { formatTime } from "../lib/format"
import { mount } from "../lib/mount"

interface OAuthClient {
  tokenId: string
  description: string
  scopes: string[]
  lastActivity: string | null
  created: string | null
}

interface TokenConfig {
  /** Server-rendered <option> list for token expiration (<select> inner HTML). */
  tokenExpiresInOptionsHtml: string
  oauthClients: OAuthClient[]
}

interface ExpiryOption {
  value: string
  label: string
}

/** Parse the hub-rendered expiration <option> list so we stay in lockstep with admin config. */
function parseExpiryOptions(html: string): ExpiryOption[] {
  if (!html) return []
  const doc = new DOMParser().parseFromString(html, "text/html")
  return Array.from(doc.querySelectorAll("option")).map((o) => ({
    value: o.getAttribute("value") ?? "",
    label: o.textContent?.trim() ?? "",
  }))
}

/** Revoke is irreversible (scripts using the token lose access) — always confirm first. */
function RevokeButton({ revoke }: { revoke: () => void }) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="error">
          <Trash2 size={14} />
          Revoke
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revoke this token?</AlertDialogTitle>
          <AlertDialogDescription>
            Applications and scripts using this token will lose access immediately and cannot be restored. Revoking a
            token for a running server requires restarting that server.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={revoke}>Revoke</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export function TokenPage() {
  const cfg = getAppConfig<TokenConfig>({
    tokenExpiresInOptionsHtml: "",
    oauthClients: [],
  })
  const api = useMemo(() => new HubApi(cfg.baseUrl, cfg.xsrf), [cfg.baseUrl, cfg.xsrf])

  const expiryOptions = useMemo(
    () => parseExpiryOptions(cfg.tokenExpiresInOptionsHtml),
    [cfg.tokenExpiresInOptionsHtml]
  )
  const defaultExpiry = expiryOptions.length ? expiryOptions[0].value : ""

  const [tokens, setTokens] = useState<HubTokenModel[]>([])
  const [note, setNote] = useState("")
  const [expiry, setExpiry] = useState(defaultExpiry)
  const [scopes, setScopes] = useState("")
  const [busy, setBusy] = useState(false)
  const [newToken, setNewToken] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const refresh = useCallback(() => {
    api
      .listTokens(cfg.userName)
      .then((reply) => setTokens(reply.api_tokens))
      .catch((e: Error) => toast.error(e.message))
  }, [api, cfg.userName])

  useEffect(refresh, [refresh])

  // JH auto-generates server-spawn tokens ("Server at /user/<name>/"); keep them separate.
  const userTokens = useMemo(() => tokens.filter((t) => !t.note?.startsWith("Server at /user/")), [tokens])
  const serverTokens = useMemo(() => tokens.filter((t) => t.note?.startsWith("Server at /user/")), [tokens])

  const requestToken = () => {
    setBusy(true)
    setNewToken(null)
    const scopeList = scopes
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    const expirySeconds = parseInt(expiry, 10)
    api
      .requestToken(cfg.userName, {
        note: note || "Requested via token page",
        expires_in: isNaN(expirySeconds) ? null : expirySeconds,
        ...(scopeList.length ? { scopes: scopeList } : {}),
      })
      .then((reply) => {
        setNewToken(reply.token)
        toast.success("Token created.")
        refresh()
      })
      .catch((e: Error) => toast.error(e.message))
      .finally(() => setBusy(false))
  }

  const revokeToken = (tokenId: string) => {
    api
      .revokeToken(cfg.userName, tokenId)
      .then(() => {
        toast.success("Token revoked.")
        refresh()
      })
      .catch((e: Error) => toast.error(e.message))
  }

  const copyToken = () => {
    if (newToken) {
      navigator.clipboard
        .writeText(newToken)
        .then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        })
        .catch(() => toast.error("Could not copy to clipboard."))
    }
  }

  return (
    <AuthedLayout
      baseUrl={cfg.baseUrl}
      userName={cfg.userName}
      adminAccess={cfg.adminAccess}
      logoutUrl={cfg.logoutUrl}
      current="token"
      announcement={cfg.announcement}
    >
      <PageBody>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="text-primary" size={20} />
              New API token
            </CardTitle>
            <CardDescription>Create a token for scripts and command-line access</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="token-note">Note</Label>
              <Input
                id="token-note"
                placeholder="note to identify your new token"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Small className="text-text-muted">This note helps you remember what the token is for.</Small>
            </div>
            {expiryOptions.length > 0 ? (
              <div className="flex flex-col gap-2">
                <Label>Token expires in</Label>
                <Select value={expiry} onValueChange={setExpiry}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {expiryOptions.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            <div className="flex flex-col gap-2">
              <Label htmlFor="token-scopes">Permissions</Label>
              <Input
                id="token-scopes"
                placeholder="space-separated scopes (leave empty for full access)"
                value={scopes}
                onChange={(e) => setScopes(e.target.value)}
              />
              <Small className="text-text-muted">
                Limit the token so it can only do what you want. Empty means full access.
              </Small>
            </div>
            <Button onClick={requestToken} disabled={busy}>
              Request new API token
            </Button>
          </CardContent>
        </Card>

        {newToken ? (
          <Alert variant="success">
            <AlertTitle>Your new API token</AlertTitle>
            <AlertDescription className="flex flex-col gap-2">
              <code className="bg-surface line-clamp-none rounded px-2 py-1 font-mono text-sm break-all">
                {newToken}
              </code>
              <div>
                <Button size="sm" variant="secondary" onClick={copyToken}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? "Copied" : "Copy token"}
                </Button>
              </div>
              <Small className="text-text-muted">You won't be able to see this token again — store it now.</Small>
            </AlertDescription>
          </Alert>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>API tokens</CardTitle>
            <CardDescription>
              Tokens with access to the JupyterHub API. Revoking a token for a running server requires restarting that
              server.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {userTokens.length === 0 ? (
              <P className="text-text-muted">You have no API tokens.</P>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Note</TableHead>
                      <TableHead>Last used</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Expires</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {userTokens.map((t) => (
                      <TableRow key={t.id}>
                        <TableCell>
                          <div className="font-medium">{t.note || "(no note)"}</div>
                          {t.scopes?.length ? (
                            <details>
                              <summary className="text-text-muted cursor-pointer text-xs">scopes</summary>
                              {t.scopes.map((s) => (
                                <code key={s} className="bg-surface mr-1 rounded px-1 py-0.5 font-mono text-xs">
                                  {s}
                                </code>
                              ))}
                            </details>
                          ) : null}
                        </TableCell>
                        <TableCell>{formatTime(t.last_activity)}</TableCell>
                        <TableCell>{t.created ? formatTime(t.created) : "N/A"}</TableCell>
                        <TableCell>{formatTime(t.expires_at)}</TableCell>
                        <TableCell>
                          <RevokeButton revoke={() => revokeToken(t.id)} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {serverTokens.length > 0 ? (
              <details className="mt-4">
                <summary className="text-text-muted cursor-pointer text-sm">
                  {serverTokens.length} server token{serverTokens.length !== 1 ? "s" : ""} (auto-generated)
                </summary>
                <div className="mt-2 overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Note</TableHead>
                        <TableHead>Last used</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {serverTokens.map((t) => (
                        <TableRow key={t.id}>
                          <TableCell className="text-text-muted text-sm">{t.note}</TableCell>
                          <TableCell className="text-text-muted text-sm">{formatTime(t.last_activity)}</TableCell>
                          <TableCell className="text-text-muted text-sm">{formatTime(t.created)}</TableCell>
                          <TableCell>
                            <Button size="sm" variant="error" onClick={() => revokeToken(t.id)}>
                              <Trash2 size={14} />
                              Revoke
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </details>
            ) : null}
          </CardContent>
        </Card>

        {cfg.oauthClients.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>Authorized applications</CardTitle>
              <CardDescription>
                Applications that use OAuth with JupyterHub to identify you (mostly notebook servers).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Application</TableHead>
                      <TableHead>Permissions</TableHead>
                      <TableHead>Last used</TableHead>
                      <TableHead>First authorized</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cfg.oauthClients.map((c) => (
                      <TableRow key={c.tokenId}>
                        <TableCell>{c.description}</TableCell>
                        <TableCell>
                          <details>
                            <summary className="text-text-muted cursor-pointer text-xs">scopes</summary>
                            {c.scopes.map((s) => (
                              <code key={s} className="bg-surface mr-1 rounded px-1 py-0.5 font-mono text-xs">
                                {s}
                              </code>
                            ))}
                          </details>
                        </TableCell>
                        <TableCell>{formatTime(c.lastActivity)}</TableCell>
                        <TableCell>{formatTime(c.created)}</TableCell>
                        <TableCell>
                          <RevokeButton revoke={() => revokeToken(c.tokenId)} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </PageBody>
    </AuthedLayout>
  )
}

mount(<TokenPage />)

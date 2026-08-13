import type { ReactNode } from "react"

import { Link, Muted, Small } from "@e-infra/design-system"
import { Clock, type LucideIcon } from "lucide-react"

/** Shared hero chrome for the hub status pages (home, spawn, spawn_pending, stop_pending, not_running). */

/** Centered hero shell. */
export function PageHero({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-6 text-center">
      {children}
    </div>
  )
}

type StatusTone = "primary" | "success" | "error"

const TONE_CLASSES: Record<StatusTone, string> = {
  primary: "bg-primary text-primary-foreground",
  success: "bg-success text-success-foreground",
  error: "bg-error text-error-foreground",
}

/** Decorative status circle at the top of every hero. */
export function StatusIcon({ tone, icon: Icon }: { tone: StatusTone; icon: LucideIcon }) {
  return (
    <div aria-hidden="true" className={`flex h-16 w-16 items-center justify-center rounded-full ${TONE_CLASSES[tone]}`}>
      <Icon size={28} />
    </div>
  )
}

/**
 * H1 + body copy block. Set `ariaLive` when the state can flip while the page
 * is open (e.g. EventSource reports a spawn failure) so screen readers announce it.
 */
export function HeroHeading({ children, ariaLive = false }: { children: ReactNode; ariaLive?: boolean }) {
  return (
    <div aria-live={ariaLive ? "polite" : undefined} className="flex flex-col gap-2">
      {children}
    </div>
  )
}

/** Small clock hint under the hero. */
export function WaitHint({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-1">
      <Clock size={14} aria-hidden="true" className="text-text-muted" />
      <Muted>{children}</Muted>
    </div>
  )
}

/** Collapsible raw event/failure log; pass `open` for failed states. */
export function DetailsLog({
  open = false,
  summary,
  children,
}: {
  open?: boolean
  summary: string
  children: ReactNode
}) {
  return (
    <details open={open} className="bg-surface w-full rounded-md p-3 text-left">
      <summary className="text-text-muted cursor-pointer text-sm">{summary}</summary>
      <div className="mt-2 flex flex-col gap-1">{children}</div>
    </details>
  )
}

/** One log line inside DetailsLog; pass pre-rendered safe `html` or plain children. */
export function LogEntry({ html, children }: { html?: string; children?: ReactNode }) {
  const className = "text-text-muted text-xs"
  if (html !== undefined) {
    return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />
  }
  return <span className={className}>{children}</span>
}

/** Support escalation link. */
export const SUPPORT_ISSUES_URL = "https://github.com/CERIT-SC/mddash/issues"

export function SupportNote() {
  return (
    <Small>
      Still not working?{" "}
      <Link href={SUPPORT_ISSUES_URL} target="_blank" rel="noreferrer">
        Contact support
      </Link>
    </Small>
  )
}

/** Caption below the Start my server action. */
export const START_HINT = "This starts your personal notebook server. It usually takes up to a minute."

/** Body copy for every spawn-failure state. */
export const FAILED_LEAD = "This usually happens when the system is busy or restarting — it is not your fault."

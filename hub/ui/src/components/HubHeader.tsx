import type { ReactNode } from "react"

import { Button, Header, HeaderContent, HeaderLeft, HeaderRight } from "@e-infra/design-system"
import { LogOut } from "lucide-react"

import { Logo } from "./Logo"
import { ThemeToggle } from "./ThemeToggle"

export interface HubHeaderProps {
  baseUrl: string
  /** Authenticated user name; null/undefined renders anonymous header (logo + theme toggle only). */
  userName?: string | null
  adminAccess?: boolean
  logoutUrl?: string
  /** Marks the current page in the nav. */
  current?: "home" | "token" | "admin"
}

function NavLink({ href, active, children }: { href: string; active?: boolean; children: ReactNode }) {
  return (
    <a
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-md px-3 py-2 text-sm font-medium no-underline transition-colors ${
        active ? "bg-surface-raised text-text-heading" : "text-text-muted hover:text-text-heading"
      }`}
    >
      {children}
    </a>
  )
}

export function HubHeader({ baseUrl, userName, adminAccess, logoutUrl, current }: HubHeaderProps) {
  return (
    <Header>
      <HeaderContent>
        <HeaderLeft>
          <a href={`${baseUrl}home`} className="flex items-center gap-3 no-underline">
            <Logo />
            <span className="text-text-muted text-sm">MDDash</span>
          </a>
          {userName ? (
            <nav aria-label="Hub navigation" className="ml-4 hidden gap-1 sm:flex">
              <NavLink href={`${baseUrl}home`} active={current === "home"}>
                Home
              </NavLink>
              <NavLink href={`${baseUrl}token`} active={current === "token"}>
                Tokens
              </NavLink>
              {adminAccess ? (
                <NavLink href={`${baseUrl}admin`} active={current === "admin"}>
                  Admin
                </NavLink>
              ) : null}
            </nav>
          ) : null}
        </HeaderLeft>
        <HeaderRight className="gap-2">
          <ThemeToggle />
          {userName ? <span className="text-text-muted hidden text-sm sm:inline">{userName}</span> : null}
          {userName && logoutUrl ? (
            <Button variant="outline" size="sm" asChild>
              <a href={logoutUrl} className="no-underline">
                <LogOut size={14} />
                Log out
              </a>
            </Button>
          ) : null}
        </HeaderRight>
      </HeaderContent>
    </Header>
  )
}

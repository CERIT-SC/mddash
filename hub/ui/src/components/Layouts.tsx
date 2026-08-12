import type { ReactNode } from "react"

import { Content, Toaster } from "@e-infra/design-system"

import { Announcement } from "./Announcement"
import { HubHeader } from "./HubHeader"
import { Logo } from "./Logo"
import { ThemeToggle } from "./ThemeToggle"

/** Wide content column for data pages (token, admin). */
export function PageBody({ children }: { children: ReactNode }) {
  return <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">{children}</div>
}

/** Standard authenticated page: header with nav, optional announcement, centered content column. */
export function AuthedLayout({
  baseUrl,
  userName,
  adminAccess,
  logoutUrl,
  current,
  announcement,
  children,
}: {
  baseUrl: string
  userName: string
  adminAccess?: boolean
  logoutUrl?: string
  current?: "home" | "token" | "admin"
  announcement?: string | null
  children: ReactNode
}) {
  return (
    <div className="bg-background text-text flex min-h-screen flex-col">
      <HubHeader
        baseUrl={baseUrl}
        userName={userName}
        adminAccess={adminAccess}
        logoutUrl={logoutUrl}
        current={current}
      />
      <Announcement html={announcement} />
      <main className="bg-background flex flex-1 flex-col">
        <Content className="flex flex-1 flex-col">{children}</Content>
      </main>
      <Toaster />
    </div>
  )
}

/** Centered card over the page canvas — for login, logout, error and status pages. */
export function CenteredLayout({
  announcement,
  maxWidth = "max-w-lg",
  children,
}: {
  announcement?: string | null
  maxWidth?: string
  children: ReactNode
}) {
  return (
    <div className="bg-background text-text flex min-h-screen flex-col">
      <div className="flex items-center justify-between px-4 py-3 md:px-6">
        <Logo />
        <ThemeToggle />
      </div>
      <Announcement html={announcement} />
      <main className="flex flex-1 items-center justify-center px-4 py-8 md:px-6">
        <div className={`w-full ${maxWidth}`}>{children}</div>
      </main>
      <Toaster />
    </div>
  )
}

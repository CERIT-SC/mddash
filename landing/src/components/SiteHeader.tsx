import { useEffect, useState } from "react"

import { Button, Header, HeaderContent, HeaderLeft, HeaderRight } from "@e-infra/design-system"
import { ArrowRight } from "lucide-react"

import einfraPurpleLogo from "../assets/einfra_purple.svg"
import einfraWhiteLogo from "../assets/einfra_white.svg"
import { ThemeToggle } from "./ThemeToggle"

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <Header
      className={`site-header fixed top-0 right-0 left-0 z-50 border-b border-transparent ${scrolled ? "scrolled" : ""}`}
    >
      <HeaderContent className="py-3">
        <HeaderLeft>
          <a href="#" className="flex items-center gap-3 no-underline">
            <img src={einfraPurpleLogo} alt="e-INFRA CZ" className="h-7 w-auto dark:hidden" />
            <img src={einfraWhiteLogo} alt="e-INFRA CZ" className="hidden h-7 w-auto dark:block" />
            <span className="text-text-muted text-sm">for Molecular dynamics simulations</span>
          </a>
        </HeaderLeft>
        <HeaderRight className="gap-2">
          <ThemeToggle />
          <nav aria-label="Site navigation">
            <Button size="sm" asChild>
              <a href="/hub/oauth_login?next=%2Fhub%2Fhome" className="no-underline">
                Try MDDash
                <ArrowRight size={14} />
              </a>
            </Button>
          </nav>
        </HeaderRight>
      </HeaderContent>
    </Header>
  )
}

import { useEffect, useState } from "react"

import { Button, Header, HeaderContent, HeaderLeft, HeaderRight } from "@e-infra/design-system"
import { ArrowRight, FlaskConical, GitBranch } from "lucide-react"

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
          <a href="#" className="flex items-center gap-2 no-underline">
            <div className="bg-primary text-primary-foreground flex h-8 w-8 items-center justify-center rounded-lg">
              <FlaskConical size={16} strokeWidth={2.5} />
            </div>
            <span className="font-display text-text-heading text-lg font-semibold">MDDash</span>
          </a>
        </HeaderLeft>
        <HeaderRight className="gap-2">
          <Button variant="ghost" size="sm" asChild>
            <a
              href="https://github.com/CERIT-SC/mddash"
              target="_blank"
              rel="noopener noreferrer"
              className="no-underline"
            >
              <GitBranch size={16} />
              <span className="hidden sm:inline">GitHub</span>
            </a>
          </Button>
          <Button size="sm" asChild>
            <a href="/hub/home" className="no-underline">
              Try MDDash
              <ArrowRight size={14} />
            </a>
          </Button>
        </HeaderRight>
      </HeaderContent>
    </Header>
  )
}

import { Button, Muted, P, Separator } from "@e-infra/design-system"
import { ExternalLink, GitBranch } from "lucide-react"

import { useReveal } from "../hooks/useReveal"

export function CtaSection() {
  const ref = useReveal()
  return (
    <section className="hero-mesh py-24">
      <div className="container mx-auto max-w-4xl px-6 text-center">
        <div ref={ref} className="reveal flex flex-col items-center gap-6">
          <Muted className="text-sm font-semibold tracking-widest uppercase">Get started</Muted>
          <h2 className="font-display text-text-heading text-4xl leading-tight font-semibold lg:text-5xl">
            Ready to run your next
            <br />
            simulation?
          </h2>
          <P className="text-text-muted max-w-xl">
            The e-INFRA CZ instance is live. Authenticate with your institutional account and get an isolated workspace
            in seconds.
          </P>

          <div className="mt-2 flex flex-wrap justify-center gap-4">
            <Button size="lg" asChild>
              <a href="/hub/oauth_login?next=%2Fhub%2Fhome" className="no-underline">
                Launch MDDash
                <ExternalLink size={15} />
              </a>
            </Button>
            <Button size="lg" variant="secondary" asChild>
              <a
                href="https://github.com/CERIT-SC/mddash"
                target="_blank"
                rel="noopener noreferrer"
                className="no-underline"
              >
                <GitBranch size={16} />
                View source on GitHub
              </a>
            </Button>
          </div>

          <Separator className="mx-auto my-4 max-w-xs opacity-30" />

          <P className="text-text-muted text-xs">MIT License · Open source · Deployable on any Kubernetes cluster</P>
        </div>
      </div>
    </section>
  )
}

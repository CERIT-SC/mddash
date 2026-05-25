import { Button, Muted, P, Separator } from "@e-infra/design-system"
import { ExternalLink, GitBranch } from "lucide-react"
import { useReveal } from "../hooks/useReveal"

export function CtaSection() {
  const ref = useReveal()
  return (
    <section className="py-24 hero-mesh">
      <div className="container mx-auto max-w-4xl px-6 text-center">
        <div ref={ref} className="reveal flex flex-col items-center gap-6">
          <Muted className="text-sm uppercase tracking-widest font-semibold">
            Get started
          </Muted>
          <h2 className="font-display text-4xl lg:text-5xl font-semibold text-text-heading leading-tight">
            Ready to run your next
            <br />
            simulation?
          </h2>
          <P className="text-text-muted max-w-xl">
            The e-INFRA CZ instance is live. Authenticate with your
            institutional account and get an isolated workspace in seconds.
          </P>

          <div className="flex flex-wrap gap-4 justify-center mt-2">
            <Button size="lg" asChild>
              <a href="/hub/home" className="no-underline">
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

          <Separator className="my-4 max-w-xs mx-auto opacity-30" />

          <P className="text-xs text-text-muted">
            MIT License · Open source · Deployable on any Kubernetes cluster
          </P>
          <P className="text-xs text-text-muted">
            Developed with support from{" "}
            <strong className="text-text">e-INFRA CZ</strong> (ID: 90254),
            Ministry of Education, Youth and Sports of the Czech Republic
          </P>
        </div>
      </div>
    </section>
  )
}

import { Badge, Button } from "@e-infra/design-system"
import { ArrowRight, Rocket } from "lucide-react"

import dashImg from "../assets/dash.png"
import { useReveal } from "../hooks/useReveal"

export function HeroSection() {
  const ref = useReveal()
  return (
    <section className="hero-mesh flex min-h-screen items-center pt-16">
      <div className="container mx-auto grid max-w-7xl items-center gap-16 px-6 py-24 lg:grid-cols-2">
        <div ref={ref} className="reveal flex flex-col gap-6">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className="text-xs font-medium">
              <Rocket size={11} className="mr-1" />
              Beta
            </Badge>
          </div>

          <h1 className="font-display text-text-heading text-5xl leading-[1.08] font-bold tracking-tight lg:text-6xl">
            A Virtual Research Environment for <span className="text-secondary block">Molecular Dynamics</span>
          </h1>

          <p className="text-text-muted max-w-lg text-lg leading-relaxed">
            Prepare, tune, run, analyze, and publish MD simulations without leaving the browser. One platform for the
            full lifecycle.
          </p>

          <div className="flex flex-wrap gap-3">
            <Button size="lg" asChild>
              <a href="/hub/oauth_login?next=%2Fhub%2Fhome" className="no-underline">
                Try MDDash
                <ArrowRight size={16} />
              </a>
            </Button>
          </div>
        </div>

        <div className="reveal reveal-delay-2 flex justify-center lg:justify-end" ref={useReveal()}>
          <div className="w-full max-w-2xl">
            <div className="screen-frame overflow-hidden">
              <div className="bg-surface border-border/50 flex items-center gap-2 rounded-t-lg border-b px-4 py-3">
                <div className="flex gap-1.5">
                  <span className="bg-error h-3 w-3 rounded-full opacity-70" />
                  <span className="bg-warning h-3 w-3 rounded-full opacity-70" />
                  <span className="bg-success h-3 w-3 rounded-full opacity-70" />
                </div>
              </div>
              <img src={dashImg} alt="MDDash dashboard" className="block w-full" width={2435} height={2298} />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

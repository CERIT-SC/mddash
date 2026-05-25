import { Badge, Button, Strong } from "@e-infra/design-system"
import { ArrowRight, CheckCircle, GitBranch, Globe, Rocket } from "lucide-react"
import dashImg from "../assets/dash.png"
import { useReveal } from "../hooks/useReveal"

export function HeroSection() {
  const ref = useReveal()
  return (
    <section className="hero-mesh min-h-screen flex items-center pt-16">
      <div className="container mx-auto max-w-7xl px-6 py-24 grid lg:grid-cols-2 gap-16 items-center">
        <div ref={ref} className="reveal flex flex-col gap-6">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className="text-xs font-medium">
              <Rocket size={11} className="mr-1" />
              Now in beta
            </Badge>
            <Badge variant="outline" className="text-xs font-medium">
              <Globe size={11} className="mr-1" />
              e-INFRA CZ platform
            </Badge>
          </div>

          <h1 className="font-display text-5xl lg:text-6xl font-semibold leading-[1.08] text-text-heading">
            A Virtual Research Environment for Molecular Dynamics
          </h1>

          <p className="text-lg text-text-muted leading-relaxed max-w-lg">
            Prepare, tune, run, analyze, and publish MD simulations — without
            leaving the browser. One platform for the full lifecycle.
          </p>

          <div className="flex flex-wrap gap-3">
            <Button size="lg" asChild>
              <a href="/hub/home" className="no-underline">
                Try MDDash
                <ArrowRight size={16} />
              </a>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <a
                href="https://github.com/CERIT-SC/mddash"
                target="_blank"
                rel="noopener noreferrer"
                className="no-underline"
              >
                <GitBranch size={16} />
                Source code
              </a>
            </Button>
          </div>

          <div className="flex items-center gap-4 pt-2">
            <div className="h-px flex-1 bg-border" />
            <div className="flex items-center gap-6 text-sm">
              <span className="flex items-center gap-1.5 text-text-muted">
                <CheckCircle size={14} className="text-success shrink-0" />
                <span>
                  <Strong className="text-text">~75%</Strong> less setup time
                </span>
              </span>
              <span className="flex items-center gap-1.5 text-text-muted">
                <CheckCircle size={14} className="text-success shrink-0" />
                <span>
                  <Strong className="text-text">No</Strong> terminal required
                </span>
              </span>
            </div>
            <div className="h-px flex-1 bg-border" />
          </div>
        </div>

        <div className="reveal reveal-delay-2 flex justify-center lg:justify-end" ref={useReveal()}>
          <div className="w-full max-w-2xl">
            <div className="screen-frame overflow-hidden">
              <div className="bg-surface rounded-t-lg border-b border-border/50 px-4 py-3 flex items-center gap-2">
                <div className="flex gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-error opacity-70" />
                  <span className="w-3 h-3 rounded-full bg-warning opacity-70" />
                  <span className="w-3 h-3 rounded-full bg-success opacity-70" />
                </div>
                <div className="mx-auto flex items-center gap-2 text-xs text-text-muted bg-surface rounded-md px-3 py-1">
                  <Globe size={10} />
                  MDDash
                </div>
              </div>
              <img src={dashImg} alt="MDDash dashboard" className="w-full block" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

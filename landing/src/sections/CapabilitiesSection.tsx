import { Card, CardContent, CardDescription, CardHeader, CardIcon, CardTitle, H2, Muted } from "@e-infra/design-system"
import { BookOpen, Cloud, GitFork, Globe, Microscope, RefreshCw, Server, Shield, type LucideIcon } from "lucide-react"

import { useReveal } from "../hooks/useReveal"

type Capability = {
  icon: LucideIcon
  title: string
  body: string
}

const CAPABILITIES: Capability[] = [
  {
    icon: RefreshCw,
    title: "Reproducibility by design",
    body: "Every step captures metadata. Notebooks make procedures executable and self-documenting. Experiments can be created directly from any published MDRepo record.",
  },
  {
    icon: Globe,
    title: "No installation, no terminal",
    body: "Authenticate via e-INFRA CZ OIDC, get an isolated workspace with persistent storage, and start working immediately from a browser.",
  },
  {
    icon: Server,
    title: "Multi-engine support",
    body: "GROMACS as the primary engine, AMBER as an alternative. Engine-specific logic is abstracted so additional engines can be added without touching workflow logic.",
  },
  {
    icon: BookOpen,
    title: "Bring your own notebooks",
    body: "A curated notebook collection ships with the platform. Research groups can plug in their own Git or Binder-compatible repositories.",
  },
  {
    icon: Microscope,
    title: "Integrated visualization",
    body: "Mol* embedded for collaborative inspection of large structural datasets, available during active runs for early issue detection.",
  },
  {
    icon: Shield,
    title: "FAIR data out of the box",
    body: "Direct integration with MDRepo enforces MD-specific metadata schemas and standardized trajectory formats. Every experiment gets a persistent DOI.",
  },
  {
    icon: Cloud,
    title: "Cloud-native execution",
    body: "Kubernetes Jobs manage execution with resource quotas. Jobs survive browser disconnects and pod restarts — no babysitting required.",
  },
  {
    icon: GitFork,
    title: "Open source",
    body: "MIT license. Deploy on your own Kubernetes infrastructure or use the e-INFRA CZ instance. Extend, fork, and contribute.",
  },
]

type CapabilityCardProps = {
  icon: LucideIcon
  title: string
  body: string
  delay: number
}

function CapabilityCard({ icon: Icon, title, body, delay }: CapabilityCardProps) {
  const ref = useReveal()
  return (
    <div ref={ref} className={`reveal reveal-delay-${delay} transition-transform duration-200 hover:-translate-y-0.5`}>
      <Card className="h-full">
        <CardHeader>
          <CardIcon className="text-primary">
            <Icon size={18} />
          </CardIcon>
          <CardTitle className="mt-3 text-sm font-semibold">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription className="text-xs leading-relaxed">{body}</CardDescription>
        </CardContent>
      </Card>
    </div>
  )
}

export function CapabilitiesSection() {
  const ref = useReveal()
  return (
    <section className="bg-background py-24">
      <div className="container mx-auto max-w-7xl px-6">
        <div ref={ref} className="reveal mb-16 text-center">
          <Muted className="mb-3 text-sm font-semibold tracking-widest uppercase">Capabilities</Muted>
          <H2 className="font-display text-text-heading mb-4 text-3xl lg:text-4xl">Built for research, not demos</H2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map(({ icon, title, body }, i) => (
            <CapabilityCard key={title} icon={icon} title={title} body={body} delay={(i % 4) + 1} />
          ))}
        </div>
      </div>
    </section>
  )
}

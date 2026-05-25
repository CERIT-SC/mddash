import { P } from "@e-infra/design-system"

import { useReveal } from "../hooks/useReveal"

export function SpeedStat() {
  const ref = useReveal()
  return (
    <section className="bg-surface py-16">
      <div className="container mx-auto max-w-3xl px-6">
        <div ref={ref} className="reveal flex flex-col items-center gap-8 text-center sm:flex-row sm:text-left">
          <div className="shrink-0">
            <span className="font-display text-gradient text-8xl leading-none font-semibold">~75%</span>
          </div>
          <div>
            <P className="text-text mb-2 text-lg leading-snug font-semibold">
              less active setup time compared to a manual command-line workflow
            </P>
            <P className="text-text-muted text-sm leading-relaxed">
              Automated performance tuning alone prevents days of wasted compute on multi-week production runs — the
              advantage compounds the longer the simulation.
            </P>
          </div>
        </div>
      </div>
    </section>
  )
}

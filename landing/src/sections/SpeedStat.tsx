import { P } from "@e-infra/design-system"
import { useReveal } from "../hooks/useReveal"

export function SpeedStat() {
  const ref = useReveal()
  return (
    <section className="py-16 bg-surface">
      <div className="container mx-auto max-w-3xl px-6">
        <div
          ref={ref}
          className="reveal flex flex-col sm:flex-row items-center gap-8 text-center sm:text-left"
        >
          <div className="shrink-0">
            <span className="font-display text-8xl font-semibold text-gradient leading-none">
              ~75%
            </span>
          </div>
          <div>
            <P className="text-text font-semibold text-lg leading-snug mb-2">
              less active setup time compared to a manual command-line workflow
            </P>
            <P className="text-text-muted text-sm leading-relaxed">
              Automated performance tuning alone prevents days of wasted compute
              on multi-week production runs — the advantage compounds the longer
              the simulation.
            </P>
          </div>
        </div>
      </div>
    </section>
  )
}

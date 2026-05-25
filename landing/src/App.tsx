import { GlowSeparator } from "./components/GlowSeparator"
import { SiteFooter } from "./components/SiteFooter"
import { SiteHeader } from "./components/SiteHeader"
import { CapabilitiesSection } from "./sections/CapabilitiesSection"
import { CtaSection } from "./sections/CtaSection"
import { HeroSection } from "./sections/HeroSection"
import { SpeedStat } from "./sections/SpeedStat"
import { WizardSection } from "./sections/WizardSection"

export default function App() {
  return (
    <div className="min-h-screen bg-background text-text">
      <SiteHeader />
      <main>
        <HeroSection />
        <GlowSeparator />
        <CapabilitiesSection />
        <GlowSeparator />
        <WizardSection />
        <SpeedStat />
        <GlowSeparator />
        <CtaSection />
      </main>
      <SiteFooter />
    </div>
  )
}

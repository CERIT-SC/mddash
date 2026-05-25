import { Footer } from "@e-infra/design-system"

import { GlowSeparator } from "./GlowSeparator"

export function SiteFooter() {
  return (
    <>
      <GlowSeparator />
      {/* sr-only h3 bridges the h2→h4 gap introduced by the design system Footer */}
      <h3 className="sr-only">Site footer</h3>
      <Footer tag="Developed with support from e-INFRA CZ (ID: 90254), Ministry of Education, Youth and Sports of the Czech Republic" />
    </>
  )
}

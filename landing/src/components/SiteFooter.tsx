import {
  Footer,
  FooterContent,
  FooterLeft,
  FooterLeftText,
  FooterLogo,
  FooterMeta,
  FooterNavLink,
  Separator,
} from "@e-infra/design-system"

import einfraPurpleLogo from "../assets/einfra_purple.svg"
import einfraWhiteLogo from "../assets/einfra_white.svg"
import { GlowSeparator } from "./GlowSeparator"

export function SiteFooter() {
  return (
    <>
      <GlowSeparator />
      <Footer>
        <FooterContent>
          <FooterLeft>
            <FooterLogo>
              <img src={einfraPurpleLogo} alt="e-INFRA CZ" className="h-12 w-auto dark:hidden" />
              <img src={einfraWhiteLogo} alt="e-INFRA CZ" className="hidden h-12 w-auto dark:block" />
            </FooterLogo>
            <FooterLeftText>
              Developed with support from e-INFRA CZ (ID: 90254), Ministry of Education, Youth and Sports of the Czech
              Republic
            </FooterLeftText>
          </FooterLeft>
        </FooterContent>
        <FooterMeta>
          <div className="flex items-center gap-2">
            <p className="text-text-muted text-sm">Copyright © {new Date().getFullYear()} e-INFRA CZ</p>
            <Separator orientation="vertical" className="h-4" />
            <FooterNavLink href="https://www.e-infra.cz/en/personal-data-processing">
              Personal data processing
            </FooterNavLink>
          </div>
        </FooterMeta>
      </Footer>
    </>
  )
}

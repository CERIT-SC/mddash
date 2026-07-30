import einfraPurpleLogo from "../assets/einfra_purple.svg"
import einfraWhiteLogo from "../assets/einfra_white.svg"

/** e-INFRA brand logo pair switching with the theme. */
export function Logo() {
  return (
    <>
      <img src={einfraPurpleLogo} alt="e-INFRA CZ" className="h-7 w-auto dark:hidden" />
      <img src={einfraWhiteLogo} alt="e-INFRA CZ" className="hidden h-7 w-auto dark:block" />
    </>
  )
}

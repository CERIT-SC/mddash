import { useState } from "react"

import purpleLogo from "@/assets/einfra-purple.svg"
import whiteLogo from "@/assets/einfra-white.svg"
import {
  Button,
  Header,
  HeaderContent,
  HeaderLeft,
  HeaderRight,
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
} from "@e-infra/design-system"
import { Link } from "@tanstack/react-router"
import { LogOut, Moon, Sun } from "lucide-react"

type SiteHeaderProps = {
  user: string
}

// Hub routes are the same on every deployment — no need for runtime configuration.
const HUB_HOME_URL = "/hub/home"
const HUB_TOKEN_URL = "/hub/token"
const LOGOUT_URL = "/hub/logout"

export function SiteHeader({ user }: SiteHeaderProps) {
  const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains("dark"))

  function toggleTheme() {
    const next = !isDark
    document.documentElement.classList.toggle("dark", next)
    document.documentElement.style.colorScheme = next ? "dark" : "light"
    try {
      localStorage.setItem("theme", next ? "dark" : "light")
    } catch {}
    setIsDark(next)
  }
  return (
    <Header>
      <HeaderContent>
        <HeaderLeft>
          <Link to="/" aria-label="MDDash home" className="flex items-center gap-3 no-underline">
            <img src={purpleLogo} alt="" className="h-7 w-auto dark:hidden" />
            <img src={whiteLogo} alt="" className="hidden h-7 w-auto dark:block" />
            <span className="text-text-muted text-sm">MDDash</span>
          </Link>
          <NavigationMenu className="ml-4 hidden md:flex">
            <NavigationMenuList>
              <NavigationMenuItem>
                <NavigationMenuLink href={HUB_HOME_URL}>Home</NavigationMenuLink>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink href={HUB_TOKEN_URL}>Get Token</NavigationMenuLink>
              </NavigationMenuItem>
            </NavigationMenuList>
          </NavigationMenu>
        </HeaderLeft>
        <HeaderRight className="gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </Button>
          <span className="text-text-muted hidden text-sm sm:inline">{user}</span>
          <Button variant="outline" size="sm" asChild>
            <a href={LOGOUT_URL} aria-label="Log out" className="no-underline">
              <LogOut size={14} />
              <span className="hidden sm:inline">Log out</span>
            </a>
          </Button>
        </HeaderRight>
      </HeaderContent>
    </Header>
  )
}

import purpleLogo from "@/assets/einfra-purple.svg"
import whiteLogo from "@/assets/einfra-white.svg"
import { useTheme } from "@/shared/hooks/use-theme"
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
  hubHomeUrl: string
  hubTokenUrl: string
  logoutUrl: string
}

export function SiteHeader({ user, hubHomeUrl, hubTokenUrl, logoutUrl }: SiteHeaderProps) {
  const { isDark, toggleTheme } = useTheme()
  return (
    <Header>
      <HeaderContent>
        <HeaderLeft>
          <Link to="/" aria-label="MDDash home" className="flex items-center gap-3 no-underline">
            <img src={purpleLogo} alt="" className="h-7 w-auto dark:hidden" />
            <img src={whiteLogo} alt="" className="hidden h-7 w-auto dark:block" />
            <span className="text-text-muted text-sm">MDDash</span>
          </Link>
          <NavigationMenu className="ml-4">
            <NavigationMenuList>
              <NavigationMenuItem>
                <NavigationMenuLink href={hubHomeUrl}>Home</NavigationMenuLink>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink href={hubTokenUrl}>Get Token</NavigationMenuLink>
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
            <a href={logoutUrl} className="no-underline">
              <LogOut size={14} />
              Log out
            </a>
          </Button>
        </HeaderRight>
      </HeaderContent>
    </Header>
  )
}

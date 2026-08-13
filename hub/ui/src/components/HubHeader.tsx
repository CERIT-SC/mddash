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
import { LogOut } from "lucide-react"

import { Logo } from "./Logo"
import { ThemeToggle } from "./ThemeToggle"

export interface HubHeaderProps {
  baseUrl: string
  /** Authenticated user name; null/undefined renders anonymous header (logo + theme toggle only). */
  userName?: string | null
  adminAccess?: boolean
  logoutUrl?: string
  /** Marks the current page in the nav. */
  current?: "home" | "token" | "admin"
}

export function HubHeader({ baseUrl, userName, adminAccess, logoutUrl, current }: HubHeaderProps) {
  return (
    <Header>
      <HeaderContent>
        <HeaderLeft>
          <a href={`${baseUrl}home`} className="flex items-center gap-3 no-underline">
            <Logo />
            <span className="text-text-muted text-sm">MDDash</span>
          </a>
          {userName ? (
            <NavigationMenu className="ml-4">
              <NavigationMenuList>
                <NavigationMenuItem>
                  <NavigationMenuLink href={`${baseUrl}home`} active={current === "home"}>
                    Home
                  </NavigationMenuLink>
                </NavigationMenuItem>
                <NavigationMenuItem>
                  <NavigationMenuLink href={`${baseUrl}token`} active={current === "token"}>
                    Get Token
                  </NavigationMenuLink>
                </NavigationMenuItem>
                {adminAccess ? (
                  <NavigationMenuItem>
                    <NavigationMenuLink href={`${baseUrl}admin`} active={current === "admin"}>
                      Admin
                    </NavigationMenuLink>
                  </NavigationMenuItem>
                ) : null}
              </NavigationMenuList>
            </NavigationMenu>
          ) : null}
        </HeaderLeft>
        <HeaderRight className="gap-2">
          <ThemeToggle />
          {userName ? <span className="text-text-muted hidden text-sm sm:inline">{userName}</span> : null}
          {userName && logoutUrl ? (
            <Button variant="outline" size="sm" asChild>
              <a href={logoutUrl} className="no-underline">
                <LogOut size={14} />
                Log out
              </a>
            </Button>
          ) : null}
        </HeaderRight>
      </HeaderContent>
    </Header>
  )
}

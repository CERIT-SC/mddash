import { useContext, type ReactNode } from "react"

import { ThemeContext } from "@/ThemeContext"
import { Link } from "@tanstack/react-router"
import { LogOut, Moon, Sun } from "lucide-react"

import { USER } from "@/util/const"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="text-primary-foreground/80 hover:bg-foreground/10 hover:text-primary-foreground rounded-md px-3 py-2 text-sm font-medium no-underline transition-colors"
    >
      {children}
    </a>
  )
}

const Header = () => {
  const { toggleTheme, mode } = useContext(ThemeContext)

  return (
    <header className="bg-primary text-primary-foreground dark:bg-card">
      <div className="flex items-center justify-between px-4" style={{ minHeight: 64 }}>
        {/* Brand + hub navigation (mirrors the hub header; e-INFRA logo not yet available here) */}
        <div className="flex items-center gap-4">
          <Link to="/" className="text-primary-foreground hover:text-primary-foreground no-underline">
            <span className="text-lg font-semibold tracking-tight">MDDash</span>
          </Link>
          <nav aria-label="Hub navigation" className="hidden gap-1 sm:flex">
            <NavLink href="/hub/home">Home</NavLink>
            <NavLink href="/hub/token">Tokens</NavLink>
          </nav>
        </div>

        <div className="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleTheme}
                className="text-primary-foreground hover:bg-foreground/10"
                aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              >
                {mode === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}</TooltipContent>
          </Tooltip>

          <span className="text-primary-foreground/80 hidden text-sm sm:inline">{USER}</span>

          <Button
            variant="ghost"
            size="sm"
            asChild
            className="border-primary-foreground/40 text-primary-foreground hover:bg-foreground/10 border"
          >
            <a href="/hub/logout" className="no-underline">
              <LogOut />
              Log out
            </a>
          </Button>
        </div>
      </div>
    </header>
  )
}

export default Header

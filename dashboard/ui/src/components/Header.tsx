import { useContext } from "react"

import { ThemeContext } from "@/ThemeContext"
import { Link, useRouterState } from "@tanstack/react-router"
import { House, LayoutDashboard, Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const Header = () => {
  const routerState = useRouterState()
  const pathname = routerState.location.pathname
  const notHome = pathname !== "/" && pathname !== ""
  const { toggleTheme, mode } = useContext(ThemeContext)

  return (
    <header className="bg-primary text-primary-foreground dark:bg-card">
      <div className="flex items-center justify-between px-2" style={{ minHeight: 64 }}>
        {/* Left icons */}
        <div className="flex items-center" style={{ width: 96 }}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" asChild className="text-primary-foreground hover:bg-foreground/10">
                <a href="/hub/home" aria-label="Back to JupyterHub">
                  <House className="h-5 w-5" />
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Back to JupyterHub</TooltipContent>
          </Tooltip>

          {notHome && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" asChild className="text-primary-foreground hover:bg-foreground/10">
                  <Link to="/" aria-label="Back to Dashboard">
                    <LayoutDashboard className="h-5 w-5" />
                  </Link>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Back to Dashboard</TooltipContent>
            </Tooltip>
          )}
        </div>

        {/* Title */}
        <div className="flex-1 text-center">
          <Link to="/" className="text-primary-foreground hover:text-primary-foreground no-underline">
            <h1 className="text-2xl font-bold tracking-tight">MDDash</h1>
          </Link>
        </div>

        {/* Right icons */}
        <div className="flex items-center justify-end" style={{ width: 96 }}>
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
        </div>
      </div>
    </header>
  )
}

export default Header

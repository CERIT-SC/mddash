import { Button } from "@e-infra/design-system"
import { Moon, Sun } from "lucide-react"

import { useTheme } from "../hooks/useTheme"

export function ThemeToggle() {
  const { isDark, toggleTheme } = useTheme()
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Light theme" : "Dark theme"}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </Button>
  )
}

import { useCallback, useEffect, useState, type ReactNode } from "react"

import { ThemeContext } from "./ThemeContext"

const getInitialMode = (): "light" | "dark" => {
  if (typeof window === "undefined") return "light"
  const stored = localStorage.getItem("themeMode")
  if (stored === "light" || stored === "dark") return stored
  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark"
  return "light"
}

// Apply immediately at module init to avoid a flash of unstyled content on page load
const _initialMode = getInitialMode()
if (typeof document !== "undefined") {
  document.documentElement.classList.toggle("dark", _initialMode === "dark")
}

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [mode, setMode] = useState<"light" | "dark">(_initialMode)

  useEffect(() => {
    localStorage.setItem("themeMode", mode)
    document.documentElement.classList.toggle("dark", mode === "dark")
  }, [mode])

  const toggleTheme = useCallback(() => setMode((m) => (m === "light" ? "dark" : "light")), [])

  return <ThemeContext.Provider value={{ mode, toggleTheme }}>{children}</ThemeContext.Provider>
}

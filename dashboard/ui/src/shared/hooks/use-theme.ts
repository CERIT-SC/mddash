import { useEffect, useState } from "react"

export const THEME_STORAGE_KEY = "theme"
type Theme = "light" | "dark"

function currentTheme(): Theme {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === "light" || stored === "dark") return stored
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    document.documentElement.style.colorScheme = theme
  }, [theme])

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark"
    window.localStorage.setItem(THEME_STORAGE_KEY, next)
    setTheme(next)
  }

  return { isDark: theme === "dark", toggleTheme }
}

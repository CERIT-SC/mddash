import { useCallback, useEffect, useState } from "react"

export type Theme = "light" | "dark"

const STORAGE_KEY = "theme"

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

function storedTheme(): Theme | null {
  const value = localStorage.getItem(STORAGE_KEY)
  return value === "light" || value === "dark" ? value : null
}

function resolveTheme(): Theme {
  return storedTheme() ?? (systemPrefersDark() ? "dark" : "light")
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(resolveTheme)

  // Keep the <html> class and native color-scheme in sync with the theme.
  useEffect(() => {
    const el = document.documentElement
    el.classList.toggle("dark", theme === "dark")
    el.style.setProperty("color-scheme", theme)
  }, [theme])

  // While no explicit choice has been made, keep following the OS preference.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = (event: MediaQueryListEvent) => {
      if (storedTheme() !== null) return
      setThemeState(event.matches ? "dark" : "light")
    }
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  // An explicit choice is applied and persisted.
  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark")
  }, [theme, setTheme])

  return { theme, isDark: theme === "dark", setTheme, toggleTheme }
}

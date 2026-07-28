import { useCallback, useEffect, useState } from "react"

export type Theme = "light" | "dark"

const STORAGE_KEY = "theme"

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === "light" || value === "dark" ? value : null
  } catch {
    // Storage unavailable (e.g. privacy mode) — behave as "no stored choice".
    return null
  }
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
    const sync = () => {
      if (storedTheme() !== null) return
      setThemeState(mq.matches ? "dark" : "light")
    }
    // Re-sync on attach: initial theme derives at mount, but an OS preference
    // change could land between first render and listener attachment.
    sync()
    mq.addEventListener("change", sync)
    return () => mq.removeEventListener("change", sync)
  }, [])

  // An explicit choice is applied and persisted.
  const setTheme = useCallback((next: Theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Storage unavailable (privacy mode) — apply for this session only.
    }
    setThemeState(next)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark")
  }, [theme, setTheme])

  return { theme, isDark: theme === "dark", setTheme, toggleTheme }
}

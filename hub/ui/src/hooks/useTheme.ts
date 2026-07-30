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
    return null
  }
}

function resolveTheme(): Theme {
  return storedTheme() ?? (systemPrefersDark() ? "dark" : "light")
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(resolveTheme)

  useEffect(() => {
    const el = document.documentElement
    el.classList.toggle("dark", theme === "dark")
    el.style.setProperty("color-scheme", theme)
  }, [theme])

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const sync = () => {
      if (storedTheme() !== null) return
      setThemeState(mq.matches ? "dark" : "light")
    }
    sync()
    mq.addEventListener("change", sync)
    return () => mq.removeEventListener("change", sync)
  }, [])

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

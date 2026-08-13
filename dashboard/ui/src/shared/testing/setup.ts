import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterAll, afterEach, beforeAll, vi } from "vitest"

import { server } from "./server"

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const storage = new Map<string, string>()
Object.defineProperty(window, "localStorage", {
  value: {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    clear: () => storage.clear(),
    key: (index: number) => [...storage.keys()][index] ?? null,
    get length() {
      return storage.size
    },
  } satisfies Storage,
})

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" })
  const interceptedFetch = globalThis.fetch
  globalThis.fetch = (input, init) => {
    const url = typeof input === "string" || input instanceof URL ? new URL(input, window.location.href) : input
    return interceptedFetch(url, init)
  }
  window.scrollTo = () => undefined
})
afterEach(() => {
  cleanup()
  server.resetHandlers()
  window.localStorage.clear()
  document.documentElement.classList.remove("dark")
  document.documentElement.style.colorScheme = ""
  vi.unstubAllGlobals()
})
afterAll(() => server.close())

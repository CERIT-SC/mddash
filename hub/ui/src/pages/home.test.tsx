import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { HubServerModel, HubUserModel } from "../lib/api"
import { HomePage } from "./home"

const mocks = vi.hoisted(() => ({
  getUser: vi.fn(),
  startServer: vi.fn(),
  stopServer: vi.fn(),
}))

vi.mock("../lib/api", () => ({
  HubApi: vi.fn(function () {
    return mocks
  }),
}))
vi.mock("../lib/mount", () => ({ mount: vi.fn() }))

const HOME_URL = "http://localhost/hub/home"
const PENDING_URL = "/hub/spawn-pending/user"

function stubLocation() {
  const location = {
    href: HOME_URL,
    origin: "http://localhost",
    pathname: "/hub/home",
    search: "",
    hash: "",
    assign: vi.fn(),
    replace: vi.fn(),
    reload: vi.fn(),
  }
  Object.defineProperty(window, "location", { configurable: true, writable: true, value: location })
}

function userModel(server?: Partial<HubServerModel>): HubUserModel {
  const base = {
    name: "",
    ready: false,
    active: false,
    pending: null,
    url: "/user/user/",
    started: null,
    stopped: null,
    last_activity: null,
    progress_url: null,
    ...server,
  } as HubServerModel
  return {
    name: "user",
    admin: false,
    server: null,
    pending: null,
    created: null,
    last_activity: null,
    servers: server ? { "": base } : {},
  }
}

const stoppedUser = userModel()
const runningUser = userModel({ ready: true, active: true })

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.clearAllMocks()
  stubLocation()
  mocks.getUser.mockResolvedValue(stoppedUser)
})

describe("HomePage transitions", () => {
  it("shows transition copy during the spawn POST and navigates only after it resolves", async () => {
    render(<HomePage />)
    const startServer = deferred<void>()
    mocks.startServer.mockReturnValue(startServer.promise)

    await userEvent.click(screen.getByRole("button", { name: /start my server/i }))

    expect(screen.getByRole("heading", { name: "Starting your server…" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /start my server/i })).not.toBeInTheDocument()
    expect(window.location.href).toBe(HOME_URL)

    await act(async () => startServer.resolve(undefined))

    expect(window.location.href).toBe(PENDING_URL)
  })

  it("keeps the transition state when a stale getUser resolves after the POST", async () => {
    const getUser = deferred<HubUserModel>()
    mocks.getUser.mockReturnValue(getUser.promise)
    render(<HomePage />)
    const startServer = deferred<void>()
    mocks.startServer.mockReturnValue(startServer.promise)

    await userEvent.click(screen.getByRole("button", { name: /start my server/i }))
    await act(async () => startServer.resolve(undefined))
    await act(async () => getUser.resolve(stoppedUser))

    expect(screen.getByRole("heading", { name: "Starting your server…" })).toBeInTheDocument()
    expect(window.location.href).toBe(PENDING_URL)
  })

  it("re-enables the form when the POST fails", async () => {
    render(<HomePage />)
    const startServer = deferred<void>()
    mocks.startServer.mockReturnValue(startServer.promise)

    await userEvent.click(screen.getByRole("button", { name: /start my server/i }))
    await act(async () => startServer.reject(new Error("nope")))

    expect(await screen.findByRole("button", { name: /start my server/i })).toBeEnabled()
    expect(window.location.href).toBe(HOME_URL)
  })

  it("resets transition state when restored from bfcache", async () => {
    render(<HomePage />)
    const startServer = deferred<void>()
    mocks.startServer.mockReturnValue(startServer.promise)

    await userEvent.click(screen.getByRole("button", { name: /start my server/i }))
    await act(async () => startServer.resolve(undefined))
    expect(window.location.href).toBe(PENDING_URL)

    const pageshow = new Event("pageshow") as PageTransitionEvent
    Object.defineProperty(pageshow, "persisted", { value: true })
    await act(async () => window.dispatchEvent(pageshow))

    expect(await screen.findByRole("button", { name: /start my server/i })).toBeEnabled()
  })

  it("stop mirrors start: feedback during the POST, redirect after it resolves", async () => {
    mocks.getUser.mockResolvedValue(runningUser)
    render(<HomePage />)
    const stopButton = await screen.findByRole("button", { name: /stop my server/i })
    const stopServer = deferred<void>()
    mocks.stopServer.mockReturnValue(stopServer.promise)

    await userEvent.click(stopButton)

    expect(screen.getByRole("heading", { name: "Stopping your server…" })).toBeInTheDocument()
    expect(window.location.href).toBe(HOME_URL)

    await act(async () => stopServer.resolve(undefined))

    expect(window.location.href).toBe(PENDING_URL)
  })
})

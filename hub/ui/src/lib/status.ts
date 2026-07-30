import type { HubServerModel } from "./api"

export type ServerStatus = "stopped" | "starting" | "running" | "stopping"

/** Derive display status the same way on every page. */
export function serverStatus(server: HubServerModel | undefined): ServerStatus {
  if (!server) return "stopped"
  if (server.pending === "spawn") return "starting"
  if (server.pending === "stop") return "stopping"
  return server.ready || server.active ? "running" : "stopped"
}

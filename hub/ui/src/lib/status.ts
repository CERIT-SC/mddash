import type { HubServerModel } from "./api"

export type ServerStatus = "stopped" | "starting" | "running" | "stopping"

export function serverStatus(server: HubServerModel | undefined): ServerStatus {
  if (!server) return "stopped"
  if (server.pending === "spawn" || server.pending === "check") return "starting"
  if (server.pending === "stop") return "stopping"
  return server.ready || server.active ? "running" : "stopped"
}

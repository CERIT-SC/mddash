import { z } from "zod"

const pathSchema = z
  .string()
  .min(1)
  .startsWith("/")
  .transform((path) => (path === "/" ? path : path.replace(/\/+$/, "")))

const dashboardPathSchema = pathSchema.refine((path) => path.endsWith("/dash"), "basePath must end with /dash")

const hubRouteSchema = z.string().regex(/^\/hub\/[a-z-]+$/, "Hub routes must be root-relative /hub paths")

const runtimeConfigSchema = z
  .object({
    basePath: dashboardPathSchema,
    apiPath: pathSchema,
    user: z.string().min(1),
    defaultNotebooksRepo: z.url(),
    mdpositUrl: z.url(),
    hubHomeUrl: hubRouteSchema,
    hubTokenUrl: hubRouteSchema,
    logoutUrl: hubRouteSchema,
  })
  .superRefine((config, context) => {
    if (config.apiPath !== `${config.basePath}/api`) {
      context.addIssue({ code: "custom", message: "apiPath must equal basePath + /api", path: ["apiPath"] })
    }
  })

export type RuntimeConfig = Readonly<z.infer<typeof runtimeConfigSchema>>

export function parseRuntimeConfig(value: unknown): RuntimeConfig {
  if (value === undefined) {
    throw new Error("Dashboard configuration is unavailable")
  }

  return Object.freeze(runtimeConfigSchema.parse(value))
}

export const DEV_RUNTIME_CONFIG: RuntimeConfig = {
  basePath: "/dash",
  apiPath: "/dash/api",
  user: "demo",
  defaultNotebooksRepo: "https://github.com/CERIT-SC/mddash-notebooks.git",
  mdpositUrl: "https://mdposit.mddash.eu",
  hubHomeUrl: "/hub/home",
  hubTokenUrl: "/hub/token",
  logoutUrl: "/hub/logout",
}

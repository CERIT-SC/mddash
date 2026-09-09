import path from "path"

import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vitest/config"

// Dev stand-in for the JSON the production proxy generates with jq.
// Served over HTTP (never interpolated into JS); values mirror DEV_RUNTIME_CONFIG.
const DEV_RUNTIME_CONFIG = {
  basePath: "/dash",
  apiPath: "/dash/api",
  user: "demo",
  defaultNotebooksRepo: "https://github.com/sb-ncbr/mddash-notebooks.git",
  mdpositUrl: "https://mdposit.mddash.eu",
}

function devRuntimeConfig(): Plugin {
  return {
    name: "dev-runtime-config",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/dash/runtime-config.json", (_request, response) => {
        response.setHeader("Content-Type", "application/json")
        response.end(JSON.stringify(DEV_RUNTIME_CONFIG))
      })
      // The app only lives under /dash (router basepath) — landing on / would render NotFound.
      server.middlewares.use((request, response, next) => {
        if (request.url === "/" || request.url === "") {
          response.statusCode = 302
          response.setHeader("Location", "/dash/")
          response.end()
          return
        }
        next()
      })
    },
  }
}

export default defineConfig({
  base: "./",
  plugins: [
    devRuntimeConfig(),
    ...(process.env.VITEST
      ? []
      : [
          tanstackRouter({
            target: "react",
            routesDirectory: "./src/routes",
            generatedRouteTree: "./src/routeTree.gen.ts",
            routeFileIgnorePattern: "\\.test\\.",
          }),
        ]),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    projects: [
      {
        test: {
          name: "no-isolate",
          // test/setup.ts resets the DOM, fetch stubs and localStorage after every
          // test, so per-file isolation only re-creates the module graph (~3x slower).
          isolate: false,
          include: ["src/**/*.test.{ts,tsx}", "!src/features/analyze/analyze-step.test.tsx"],
        },
      },
      {
        test: {
          // Mocks ./renderers and ./mol-star; its factories must not leak into files
          // importing the same graph (wizard.test.tsx) through a shared registry.
          name: "isolate",
          include: ["src/features/analyze/analyze-step.test.tsx"],
        },
      },
    ],
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    proxy: {
      "/dash/api": {
        target: "http://localhost:8888",
        changeOrigin: true,
      },
    },
  },
})

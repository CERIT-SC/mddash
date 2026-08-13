import path from "path"

import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  base: "./",
  plugins: [
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
    setupFiles: ["./src/shared/testing/setup.ts"],
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/dash/api": {
        target: "http://localhost:8888",
        changeOrigin: true,
      },
    },
  },
})

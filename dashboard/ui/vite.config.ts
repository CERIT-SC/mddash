import path from "path"

import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
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
            quoteStyle: "double",
            semicolons: false,
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

  // Dev server configuration
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

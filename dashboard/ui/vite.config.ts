import path from "path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
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

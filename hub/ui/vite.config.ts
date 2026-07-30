import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// One HTML entry per JupyterHub template. Entry filenames must match the
// upstream template names exactly: JupyterHub looks templates up by filename
// in c.JupyterHub.template_paths.
export default defineConfig({
  // Asset URLs are absolute and go through the hub's static-file handler.
  // The built assets are copied into the image at this location; the built
  // HTML is copied to the template directory (see hub/Dockerfile).
  base: "/hub/static/hub-ui/",
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: Object.fromEntries(
        [
          "login",
          "home",
          "spawn",
          "spawn_pending",
          "stop_pending",
          "not_running",
          "token",
          "admin",
          "oauth",
          "logout",
          "error",
          "404",
        ].map((name) => [name, new URL(`./${name}.html`, import.meta.url).pathname]),
      ),
    },
  },
})

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import sharp from "sharp"
import type { Plugin } from "vite"
import { defineConfig } from "vite"
import { viteSingleFile } from "vite-plugin-singlefile"

function webpOptimize(): Plugin {
  return {
    name: "webp-optimize",
    enforce: "pre",
    apply: "build",
    async load(id) {
      if (!/\.(png|jpe?g)$/.test(id)) return null
      const buffer = await sharp(id)
        .resize({ width: 1800, withoutEnlargement: true })
        .webp({ quality: 80 })
        .toBuffer()
      return `export default "data:image/webp;base64,${buffer.toString("base64")}"`
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), webpOptimize(), viteSingleFile()],
})

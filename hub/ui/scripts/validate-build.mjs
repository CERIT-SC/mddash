#!/usr/bin/env node
/** Post-build artifact validation: every JupyterHub template entry must exist
 *  in dist/, carry the Jinja appConfig injection (preserved by Vite), and
 *  reference assets only under /hub/static/hub-ui/. */

import { readFileSync, readdirSync } from "node:fs"

// All entries must carry the same CSP; enforcing it here catches copy drift.
const CSP =
  "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; base-uri 'self'; form-action 'self'"

const ENTRIES = [
  "login.html",
  "home.html",
  "spawn.html",
  "spawn_pending.html",
  "stop_pending.html",
  "not_running.html",
  "token.html",
  "admin.html",
  "oauth.html",
  "logout.html",
  "error.html",
  "404.html",
]

let failed = false

for (const entry of ENTRIES) {
  let html
  try {
    html = readFileSync(`dist/${entry}`, "utf8")
  } catch {
    console.error(`FAIL ${entry}: missing from dist/`)
    failed = true
    continue
  }
  if (!html.includes(CSP)) {
    console.error(`FAIL ${entry}: CSP meta is missing or diverges from the shared policy`)
    failed = true
  }
  if (!html.includes("window.appConfig = {")) {
    console.error(`FAIL ${entry}: missing the window.appConfig injection`)
    failed = true
  }
  if (!html.includes("{{") || !html.includes("tojson")) {
    console.error(`FAIL ${entry}: Jinja expressions were mangled during build`)
    failed = true
  }
  const assetRefs = html.match(/(?:src|href)="\/(?!hub\/static\/)[^"]*"/g)
  if (assetRefs) {
    console.error(`FAIL ${entry}: asset URLs outside /hub/static/hub-ui/: ${assetRefs.join(", ")}`)
    failed = true
  }
}

const assets = readdirSync("dist/assets")
if (assets.length === 0) {
  console.error("FAIL dist/assets is empty")
  failed = true
}

if (failed) process.exit(1)
console.log(`OK ${ENTRIES.length} entries validated, ${assets.length} assets`)

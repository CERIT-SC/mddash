import { describe, expect, it } from "vitest"

import { escapeHtml } from "./escape-html"

describe("escapeHtml", () => {
  it("escapes the markup-bearing characters used for injection payloads", () => {
    expect(escapeHtml('<img src=x onerror="alert(1)">')).toBe("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")
    expect(escapeHtml("<script>alert('x')</script>")).toBe("&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;")
  })

  it("leaves ordinary labels untouched", () => {
    expect(escapeHtml("Protein-Membrane interaction")).toBe("Protein-Membrane interaction")
  })
})

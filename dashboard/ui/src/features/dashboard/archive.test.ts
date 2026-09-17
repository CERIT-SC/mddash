import { experiment } from "@/shared/fixtures/experiment"
import { describe, expect, it } from "vitest"

import { archiveStateLabel, groupByArchiveRecency, isArchived, isArchivedFailed, isArchiving } from "./archive"

const daysAgo = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString()

describe("isArchived", () => {
  it("is true only when archived_at is set", () => {
    expect(isArchived(experiment("a", { archived_at: daysAgo(1), archive_state: "archived" }))).toBe(true)
    expect(isArchived(experiment("b"))).toBe(false)
  })
})

describe("isArchiving", () => {
  it("covers both transitional states", () => {
    expect(isArchiving(experiment("a", { archive_state: "archiving" }))).toBe(true)
    expect(isArchiving(experiment("b", { archived_at: daysAgo(1), archive_state: "restoring" }))).toBe(true)
    expect(isArchiving(experiment("c", { archived_at: daysAgo(1), archive_state: "archived" }))).toBe(false)
    expect(isArchiving(experiment("d"))).toBe(false)
  })
})

describe("isArchivedFailed", () => {
  it("covers both failure states", () => {
    expect(isArchivedFailed(experiment("a", { archive_state: "archive_failed" }))).toBe(true)
    expect(isArchivedFailed(experiment("b", { archived_at: daysAgo(1), archive_state: "restore_failed" }))).toBe(true)
    expect(isArchivedFailed(experiment("c", { archived_at: daysAgo(1), archive_state: "archived" }))).toBe(false)
  })
})

describe("archiveStateLabel", () => {
  it("labels transitional and failed states", () => {
    expect(archiveStateLabel(experiment("a", { archive_state: "archiving" }))).toBe("Archiving…")
    expect(archiveStateLabel(experiment("b", { archived_at: daysAgo(2), archive_state: "restoring" }))).toBe(
      "Restoring…"
    )
    expect(archiveStateLabel(experiment("c", { archived_at: daysAgo(2), archive_state: "archived" }))).toBe(
      "Archived 2 days ago"
    )
    expect(archiveStateLabel(experiment("d"))).toBeNull()
  })
})

describe("groupByArchiveRecency", () => {
  it("buckets into recent/last month/older preserving input order within groups", () => {
    const groups = groupByArchiveRecency([
      experiment("now", { archived_at: daysAgo(0.5), archive_state: "archived" }),
      experiment("week", { archived_at: daysAgo(5), archive_state: "archived" }),
      experiment("month", { archived_at: daysAgo(20), archive_state: "archived" }),
      experiment("old", { archived_at: daysAgo(90), archive_state: "archived" }),
    ])
    expect(groups.map((g) => g.label)).toEqual(["Last 7 days", "Last month", "Older"])
    expect(groups[0].experiments.map((e) => e.id)).toEqual(["now", "week"])
    expect(groups[1].experiments.map((e) => e.id)).toEqual(["month"])
    expect(groups[2].experiments.map((e) => e.id)).toEqual(["old"])
  })

  it("omits empty buckets", () => {
    const groups = groupByArchiveRecency([experiment("old", { archived_at: daysAgo(90), archive_state: "archived" })])
    expect(groups.map((g) => g.label)).toEqual(["Older"])
  })
})

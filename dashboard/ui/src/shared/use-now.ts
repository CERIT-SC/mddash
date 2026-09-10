import { useEffect, useState } from "react"

/** Current time, refreshed on `intervalMs` while `active`; `undefined` until the first tick.
    Keeps `Date.now()` out of render so elapsed-time displays stay pure. */
export function useNow(active: boolean, intervalMs = 1000): number | undefined {
  const [now, setNow] = useState<number>()
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [active, intervalMs])
  return now
}

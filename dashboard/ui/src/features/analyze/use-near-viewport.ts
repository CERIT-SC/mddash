import { useCallback, useEffect, useState } from "react"

/**
 * Latches true once the element comes within `rootMargin` of the viewport. Without
 * IntersectionObserver (old browsers, jsdom) it reports true at once.
 */
export function useNearViewport<T extends Element>(rootMargin = "200px"): [(node: T | null) => void, boolean] {
  const supported = typeof IntersectionObserver !== "undefined"
  const [node, setNode] = useState<T | null>(null)
  const [near, setNear] = useState(!supported)

  useEffect(() => {
    if (near || node === null || !supported) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setNear(true)
      },
      { rootMargin }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [near, node, rootMargin, supported])

  const ref = useCallback((next: T | null) => setNode(next), [])
  return [ref, near]
}

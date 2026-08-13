export function deriveDashboardBasePath(pathname: string): string {
  const marker = "/dash"
  const markerIndex = pathname.indexOf(marker)
  if (markerIndex === -1) return "/"
  return `${pathname.slice(0, markerIndex + marker.length)}/`
}

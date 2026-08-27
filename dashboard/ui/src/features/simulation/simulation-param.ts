/** Manifest suffix the API guarantees on every simulation_path
    (`Simulation.write` rejects paths without it, `list_files` filters by it). */
const SIMULATION_SUFFIX = ".simulation.json"

/**
 * URL-facing identity of a simulation tab: the simulation_path without the
 * ".simulation.json" suffix ("nested/beta.simulation.json" → "nested/beta").
 * Idempotent, so a legacy suffixed `?simulation=` value normalizes to the same
 * string and old bookmarks keep resolving.
 */
export function simulationParam(simulationPath: string): string {
  return simulationPath.endsWith(SIMULATION_SUFFIX)
    ? simulationPath.slice(0, -SIMULATION_SUFFIX.length)
    : simulationPath
}

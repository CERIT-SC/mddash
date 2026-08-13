import { useRouteContext } from "@tanstack/react-router"

import { Welcome } from "./welcome"

export function WelcomeRoute() {
  const { config } = useRouteContext({ from: "__root__" })
  return <Welcome user={config.user} />
}

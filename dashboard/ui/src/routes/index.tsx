import { Welcome } from "@/features/welcome/welcome"
import { createFileRoute, useRouteContext } from "@tanstack/react-router"

export const Route = createFileRoute("/")({
  component: function WelcomeRoute() {
    const { config } = useRouteContext({ from: "__root__" })
    return <Welcome user={config.user} />
  },
})

import { WelcomeRoute } from "@/features/welcome/welcome-route"
import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/")({ component: WelcomeRoute })

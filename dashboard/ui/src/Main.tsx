import { StrictMode } from "react"

import { QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "@tanstack/react-router"
import { createRoot } from "react-dom/client"

import ErrorBoundary from "@/components/ErrorBoundary"

import { queryClient } from "./lib/query-client"
import { router } from "./router"
import { ThemeProvider } from "./Theme"

import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>
)

import { QueryCache, QueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (err) => toast.error(err instanceof Error ? err.message : "Request failed."),
  }),
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

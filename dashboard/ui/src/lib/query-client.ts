import { QueryCache, QueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (err, query) => {
      // Suppress some 404 errors where we expect the resource to not exist yet
      if (query.meta?.suppressError && query.state.data === undefined) return
      toast.error(err instanceof Error ? err.message : "Request failed.")
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

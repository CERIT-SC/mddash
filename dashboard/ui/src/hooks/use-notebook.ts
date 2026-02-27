import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { get_notebook, spawn_notebook, delete_notebook } from "@/util/api";
import type { Notebook } from "@/util/types";

export function useNotebook(experimentId: string, refetchInterval: number | false = false) {
    return useQuery<Notebook>({
        queryKey: ["experiment", experimentId, "notebook"],
        queryFn: async () => {
            const { data, error } = await get_notebook(experimentId);
            if (error) throw new Error(error);
            return data!;
        },
        enabled: !!experimentId,
        refetchInterval,
    });
}

export function useSpawnNotebook(experimentId: string) {
    const queryClient = useQueryClient();

    return useMutation<Notebook, Error>({
        mutationFn: async () => {
            const { data, error } = await spawn_notebook(experimentId);
            if (error) throw new Error(error);
            return data!;
        },
        onSuccess: (notebook) => {
            queryClient.setQueryData(["experiment", experimentId, "notebook"], notebook);
        },
        onError: (error: Error) => toast.error(error.message),
    });
}

export function useStopNotebook(experimentId: string) {
    const queryClient = useQueryClient();

    return useMutation<void, Error>({
        mutationFn: async () => {
            const { error } = await delete_notebook(experimentId);
            if (error) throw new Error(error);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: ["experiment", experimentId, "notebook"],
            });
        },
        onError: (error: Error) => toast.error(error.message),
    });
}

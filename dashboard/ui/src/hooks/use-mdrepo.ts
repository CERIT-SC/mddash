import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { get_mdrepo_status, publish_experiment } from "@/util/api";

interface MDRepoStatus {
    authenticated: boolean;
    mdrepo_url?: string;
}

interface PublishResponse {
    id: string;
    links?: {
        edit_html?: string;
        self_html?: string;
    };
}

export function useMDRepoStatus() {
    return useQuery<MDRepoStatus>({
        queryKey: ["mdrepo", "status"],
        queryFn: async () => {
            const { data, error } = await get_mdrepo_status();
            if (error) throw new Error(error);
            return data!;
        },
    });
}

export function usePublishExperiment() {
    return useMutation<PublishResponse, Error, string>({
        mutationFn: async (id) => {
            const { data, error } = await publish_experiment(id);
            if (error) throw new Error(error);
            return data!;
        },
        onError: (error: Error) => toast.error(error.message),
    });
}

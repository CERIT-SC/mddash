import { useQuery } from "@tanstack/react-query";

import { find_files } from "@/util/api";
import type { FileOption } from "@/util/types";

export function useFiles(experimentId: string, ext?: string | string[]) {
    return useQuery<FileOption[]>({
        queryKey: ["experiment", experimentId, "files", ext],
        queryFn: async () => {
            const { data, error } = await find_files(experimentId, ext);
            if (error) throw new Error(error);
            return data ?? [];
        },
        enabled: !!experimentId,
    });
}

import { useQuery } from "@tanstack/react-query";

import { get_metrics } from "@/util/api";
import type { ResourceUsage } from "@/util/types";

export function useMetrics() {
    return useQuery<ResourceUsage>({
        queryKey: ["metrics"],
        queryFn: async () => {
            const { data, error } = await get_metrics();
            if (error) throw new Error(error);
            return data!;
        },
    });
}

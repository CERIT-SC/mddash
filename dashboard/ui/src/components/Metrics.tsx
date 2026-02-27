import { useMemo } from "react";

import { Cpu, MemoryStick, HardDrive, Loader2 } from "lucide-react";

import { useMetrics } from "@/hooks/use-metrics";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

const formatBytes = (bytes: number): string => (bytes / 1024 ** 3).toFixed(2);
const formatMillicores = (millicores: number): string => (millicores / 1000).toFixed(2);

const Metrics = () => {
    const { data: metrics, isLoading } = useMetrics();

    const usageStats = useMemo(() => {
        if (!metrics) return null;

        const cpuUsagePercent = (metrics.requests.cpu / metrics.limits.cpu) * 100;
        const memoryUsagePercent = (metrics.requests.memory / metrics.limits.memory) * 100;
        const storageUsagePercent =
            metrics.requests.storage !== null ? (metrics.requests.storage / metrics.limits.storage) * 100 : null;

        return { cpuUsagePercent, memoryUsagePercent, storageUsagePercent };
    }, [metrics]);

    if (isLoading) {
        return (
            <div className="flex justify-center items-center min-h-32">
                <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!metrics || !usageStats) return null;

    const { cpuUsagePercent, memoryUsagePercent, storageUsagePercent } = usageStats;

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 px-4">
            {/* CPU */}
            <Card>
                <CardContent className="pt-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">CPU</p>
                            <p className="text-lg font-semibold">
                                {formatMillicores(metrics.requests.cpu)} / {formatMillicores(metrics.limits.cpu)} cores
                            </p>
                        </div>
                        <Cpu className="h-6 w-6 text-blue-500" />
                    </div>
                    <Progress
                        value={Math.min(cpuUsagePercent, 100)}
                        className={cpuUsagePercent > 80 ? "[&>div]:bg-yellow-500" : "[&>div]:bg-blue-500"}
                    />
                    <p className="text-xs text-muted-foreground">{cpuUsagePercent.toFixed(1)}% allocated</p>
                </CardContent>
            </Card>

            {/* Memory */}
            <Card>
                <CardContent className="pt-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">Memory</p>
                            <p className="text-lg font-semibold">
                                {formatBytes(metrics.requests.memory)} / {formatBytes(metrics.limits.memory)} GB
                            </p>
                        </div>
                        <MemoryStick className="h-6 w-6 text-yellow-500" />
                    </div>
                    <Progress
                        value={Math.min(memoryUsagePercent, 100)}
                        className={memoryUsagePercent > 80 ? "[&>div]:bg-red-500" : "[&>div]:bg-yellow-500"}
                    />
                    <p className="text-xs text-muted-foreground">{memoryUsagePercent.toFixed(1)}% allocated</p>
                </CardContent>
            </Card>

            {/* Storage */}
            <Card>
                <CardContent className="pt-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm text-muted-foreground">Storage</p>
                            <p className="text-lg font-semibold">
                                {metrics.requests.storage !== null ? formatBytes(metrics.requests.storage) : "N/A"} /{" "}
                                {formatBytes(metrics.limits.storage)} GB
                            </p>
                        </div>
                        <HardDrive className="h-6 w-6 text-green-500" />
                    </div>
                    {storageUsagePercent !== null ? (
                        <>
                            <Progress
                                value={Math.min(storageUsagePercent, 100)}
                                className={storageUsagePercent > 80 ? "[&>div]:bg-red-500" : "[&>div]:bg-green-500"}
                            />
                            <p className="text-xs text-muted-foreground">{storageUsagePercent.toFixed(1)}% used</p>
                        </>
                    ) : (
                        <>
                            <Progress value={undefined} className="animate-pulse" />
                            <p className="text-xs text-muted-foreground">Calculating...</p>
                        </>
                    )}
                </CardContent>
            </Card>
        </div>
    );
};

export default Metrics;

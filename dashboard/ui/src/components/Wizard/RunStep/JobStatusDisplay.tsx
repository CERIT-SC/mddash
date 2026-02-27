import { GromacsJob, getJobStatusVariant, statusBadgeClass } from "@/util/types";
import { formatDuration } from "@/util/helpers";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface JobStatusDisplayProps {
    jobStatus: GromacsJob;
}

const JobStatusDisplay = ({ jobStatus }: JobStatusDisplayProps) => {
    const isRunningWithProgress =
        jobStatus.status === "RUNNING" && jobStatus.nsteps !== null && jobStatus.nsteps_done !== null;

    const progressPercentage = isRunningWithProgress ? (jobStatus.nsteps_done! / jobStatus.nsteps!) * 100 : 0;
    const variant = getJobStatusVariant(jobStatus.status);

    return (
        <div className="flex flex-col gap-4 w-full">
            {/* Status card */}
            <div className="rounded-md border p-3 flex flex-col gap-3">
                <div className="flex items-center justify-center gap-2">
                    <span className="text-sm font-medium">Status</span>
                    <Badge variant="outline" className={cn("text-xs", statusBadgeClass(variant))}>
                        {jobStatus.status}
                    </Badge>
                </div>

                {isRunningWithProgress && (
                    <div className="flex flex-col gap-1 items-center">
                        <span className="text-sm text-muted-foreground">Progress</span>
                        <span className="text-2xl font-bold">{progressPercentage.toFixed(1)}%</span>
                        <Progress value={progressPercentage} className="w-full h-3 rounded" />
                        <span className="text-xs text-muted-foreground">
                            {jobStatus.nsteps_done!.toLocaleString()} / {jobStatus.nsteps!.toLocaleString()} steps
                        </span>
                        {jobStatus.estimated_time !== null && (
                            <span className="text-xs text-muted-foreground">
                                Estimated time remaining: {formatDuration(jobStatus.estimated_time)}
                            </span>
                        )}
                    </div>
                )}
            </div>

            {/* Job summary (after completion) */}
            {jobStatus.status === "TERMINATED" && (
                <>
                    <h3 className="text-sm font-semibold">Job Summary</h3>
                    <div className="grid grid-cols-2 gap-2">
                        {jobStatus.performance && (
                            <div className="rounded-md border p-3">
                                <p className="text-xs text-muted-foreground">Performance</p>
                                <p className="text-sm">{jobStatus.performance.toFixed(2)} ns/day</p>
                            </div>
                        )}
                        {jobStatus.start_timestamp && jobStatus.finish_timestamp && (
                            <div className="rounded-md border p-3">
                                <p className="text-xs text-muted-foreground">Total Runtime</p>
                                <p className="text-sm">
                                    {formatDuration(jobStatus.finish_timestamp - jobStatus.start_timestamp)}
                                </p>
                            </div>
                        )}
                    </div>
                </>
            )}

            {/* Simulation parameters */}
            <h3 className="text-sm font-semibold">Simulation Parameters</h3>
            <div className="grid grid-cols-2 gap-2">
                <div className="rounded-md border p-3">
                    <p className="text-xs text-muted-foreground">Processes</p>
                    <p className="text-sm">
                        {jobStatus.np} × {jobStatus.ntomp} threads
                    </p>
                </div>
                <div className="rounded-md border p-3">
                    <p className="text-xs text-muted-foreground">PME / NB</p>
                    <p className="text-sm">
                        {jobStatus.pme} / {jobStatus.nb}
                    </p>
                </div>
                {jobStatus.extra_args && (
                    <div className="rounded-md border p-3 col-span-2">
                        <p className="text-xs text-muted-foreground">Extra Arguments</p>
                        <p className="text-sm">{jobStatus.extra_args}</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default JobStatusDisplay;

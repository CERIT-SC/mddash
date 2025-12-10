import { Stack, Typography, Chip, LinearProgress, Paper, Grid2 as Grid } from "@mui/material";

import { GromacsJob, getJobStatusColor } from "@/util/types";
import { formatDuration } from "@/util/helpers";

interface JobStatusDisplayProps {
    jobStatus: GromacsJob;
}

const JobStatusDisplay = ({ jobStatus }: JobStatusDisplayProps) => {
    const isRunningWithProgress =
        jobStatus.status === "RUNNING" && jobStatus.nsteps !== null && jobStatus.nsteps_done !== null;

    const progressPercentage = isRunningWithProgress ? (jobStatus.nsteps_done! / jobStatus.nsteps!) * 100 : 0;

    return (
        <Stack spacing={2} width="100%">
            <Paper variant="outlined" sx={{ padding: 2 }}>
                <Stack direction="row" spacing={1} alignItems="center" justifyContent="center" width="100%">
                    <Typography variant="subtitle1">Status</Typography>
                    <Chip label={jobStatus.status} color={getJobStatusColor(jobStatus.status)} />
                </Stack>

                {isRunningWithProgress && (
                    <Stack spacing={1} mt={2} alignItems="center" justifyContent="center" width="100%">
                        <Typography variant="subtitle1" color="text.secondary">
                            Progress
                        </Typography>
                        <Typography variant="h3" color="text.primary">
                            {`${progressPercentage.toFixed(1)}%`}
                        </Typography>
                        <LinearProgress
                            variant="determinate"
                            value={progressPercentage}
                            sx={{ width: "100%", height: 12, borderRadius: 1 }}
                        />
                        <Typography variant="body2" color="text.secondary">
                            {`${jobStatus.nsteps_done!.toLocaleString()} / ${jobStatus.nsteps!.toLocaleString()} steps`}
                        </Typography>
                        {jobStatus.estimated_time !== null && (
                            <Typography variant="body2" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                                Estimated time remaining: {formatDuration(jobStatus.estimated_time)}
                            </Typography>
                        )}
                    </Stack>
                )}
            </Paper>

            {jobStatus.status === "TERMINATED" && (
                <>
                    <Typography variant="subtitle1">Job Summary</Typography>
                    <Grid direction="row" spacing={2} container>
                        {jobStatus.performance && (
                            <Grid size={6}>
                                <Paper variant="outlined" sx={{ padding: 2, flexGrow: 1 }}>
                                    <Typography variant="subtitle1" color="text.secondary">
                                        Performance
                                    </Typography>
                                    <Typography variant="body1">{`${jobStatus.performance.toFixed(
                                        2,
                                    )} ns/day`}</Typography>
                                </Paper>
                            </Grid>
                        )}
                        {jobStatus.start_timestamp && jobStatus.finish_timestamp && (
                            <Grid size={6}>
                                <Paper variant="outlined" sx={{ padding: 2, flexGrow: 1 }}>
                                    <Typography variant="subtitle1" color="text.secondary">
                                        Total Runtime
                                    </Typography>
                                    <Typography variant="body1">
                                        {formatDuration(jobStatus.finish_timestamp - jobStatus.start_timestamp)}
                                    </Typography>
                                </Paper>
                            </Grid>
                        )}
                    </Grid>
                </>
            )}

            <Typography variant="subtitle1">Simulation Parameters</Typography>

            <Grid direction="row" spacing={2} container>
                <Grid size={3}>
                    <Paper variant="outlined" sx={{ padding: 2, flexGrow: 1 }}>
                        <Typography variant="subtitle1" color="text.secondary">
                            Processes
                        </Typography>
                        <Typography variant="body1">
                            {jobStatus.np} × {jobStatus.ntomp} threads
                        </Typography>
                    </Paper>
                </Grid>

                <Grid size={3}>
                    <Paper variant="outlined" sx={{ padding: 2, flexGrow: 1 }}>
                        <Typography variant="subtitle1" color="text.secondary">
                            PME / NB
                        </Typography>
                        <Typography variant="body1">
                            {jobStatus.pme} / {jobStatus.nb}
                        </Typography>
                    </Paper>
                </Grid>

                {jobStatus.extra_args && (
                    <Grid size={6}>
                        <Paper variant="outlined" sx={{ padding: 2, flexGrow: 1 }}>
                            <Typography variant="subtitle1" color="text.secondary">
                                Extra Arguments
                            </Typography>
                            <Typography variant="body1">{jobStatus.extra_args}</Typography>
                        </Paper>
                    </Grid>
                )}
            </Grid>
        </Stack>
    );
};

export default JobStatusDisplay;

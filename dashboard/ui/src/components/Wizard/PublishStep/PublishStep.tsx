import { useEffect, useMemo } from "react";

import { CloudUpload, Pencil, CheckCircle, Info, Folder, HardDrive, LogIn, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { WizardStepProps } from "@/components/Wizard/Stepper";
import { useFiles } from "@/hooks/use-files";
import { useMDRepoStatus, usePublishExperiment } from "@/hooks/use-mdrepo";
import { useQueryClient } from "@tanstack/react-query";
import { get_mdrepo_auth_url } from "@/util/api";
import { formatFileSize } from "@/util/helpers";
import { Experiment } from "@/util/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const PublishStep = (props: WizardStepProps) => {
    const { experiment } = props;
    const queryClient = useQueryClient();

    const { data: mdrepoStatus, isLoading: loadingAuth } = useMDRepoStatus();
    const { data: files = [], isLoading: loadingFiles } = useFiles(experiment.id);
    const publishExperiment = usePublishExperiment();

    const isAuthenticated = mdrepoStatus?.authenticated ?? false;
    const isPublished = experiment.mdrepo_id !== null;
    const isLoading = loadingAuth || loadingFiles;

    const fileCount = files.length;
    const totalSize = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);

    // Handle OAuth callback result in URL params
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const authSuccess = params.get("mdrepo_auth");
        const authError = params.get("mdrepo_error");

        if (authSuccess === "success") {
            toast.success("Successfully authenticated with MDRepo!");
            const url = new URL(window.location.href);
            url.searchParams.delete("mdrepo_auth");
            window.history.replaceState({}, "", url.toString());
        } else if (authError) {
            toast.error(`MDRepo authentication failed: ${decodeURIComponent(authError)}`);
            const url = new URL(window.location.href);
            url.searchParams.delete("mdrepo_error");
            window.history.replaceState({}, "", url.toString());
        }
    }, []);

    const handleAuthClick = () => {
        const returnUrl = window.location.href;
        window.location.href = get_mdrepo_auth_url(returnUrl);
    };

    const handlePublishClick = () => {
        if (isPublished) {
            if (!isAuthenticated) {
                toast.error("You need to authenticate with MDRepo to view the published experiment.");
                return;
            }
            window.open(experiment.mdrepo_record_url!, "_blank");
            return;
        }

        publishExperiment.mutate(experiment.id, {
            onSuccess: (data) => {
                const recordUrl = data.links?.edit_html || data.links?.self_html;
                queryClient.setQueryData<Experiment>(["experiment", experiment.id], (old) =>
                    old
                        ? {
                              ...old,
                              mdrepo_id: data.id,
                              mdrepo_record_url: recordUrl || old.mdrepo_record_url,
                          }
                        : old,
                );
                if (recordUrl) window.open(recordUrl, "_blank");
                else if (experiment.mdrepo_record_url) window.open(experiment.mdrepo_record_url, "_blank");
            },
        });
    };

    return (
        <div className="flex justify-center p-6">
            <Card className="max-w-lg w-full">
                <CardContent className="pt-4 flex flex-col gap-4 items-center">
                    {/* Header */}
                    <div className="flex items-center gap-2">
                        <Info className="h-5 w-5 text-muted-foreground" />
                        <h2 className="text-lg font-semibold">Publish Experiment</h2>
                    </div>

                    {/* Status banner */}
                    <div
                        className={`w-full rounded-md border p-3 text-sm ${
                            isPublished
                                ? "border-green-500 bg-green-50 dark:bg-green-950 text-green-800 dark:text-green-200"
                                : "border-blue-400 bg-blue-50 dark:bg-blue-950 text-blue-800 dark:text-blue-200"
                        }`}
                    >
                        {isPublished
                            ? "This experiment is already published to MDRepo. Click below to view or edit the published version."
                            : "Publishing will upload your experiment data to MDRepo, making it publicly accessible and citable with a DOI."}
                    </div>

                    {/* Stats */}
                    {isLoading ? (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Loading...
                        </div>
                    ) : (
                        <div className="flex flex-col gap-2 w-full">
                            <div className="flex items-center gap-2 text-sm">
                                <Folder className="h-4 w-4 text-muted-foreground" />
                                <span className="font-medium text-muted-foreground">Files:</span>
                                <span>{fileCount}</span>
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                                <HardDrive className="h-4 w-4 text-muted-foreground" />
                                <span className="font-medium text-muted-foreground">Total Size:</span>
                                <span>{formatFileSize(totalSize)}</span>
                            </div>
                            {isPublished && (
                                <div className="flex items-center gap-2 text-sm">
                                    <span className="font-medium text-muted-foreground">Status:</span>
                                    <Badge className="bg-green-500 text-white text-xs gap-1">
                                        <CheckCircle className="h-3 w-3" />
                                        Published
                                    </Badge>
                                </div>
                            )}
                            {!isAuthenticated && (
                                <div className="rounded-md border border-yellow-400 bg-yellow-50 dark:bg-yellow-950 p-3 text-sm text-yellow-800 dark:text-yellow-200">
                                    You need to authenticate with MDRepo to{" "}
                                    {isPublished ? "view or edit the published experiment" : "publish your experiment"}.
                                    This is a one-time authorization using your e-INFRA CZ account.
                                </div>
                            )}
                        </div>
                    )}

                    {/* Action button */}
                    {!isAuthenticated ? (
                        <Button
                            variant="default"
                            size="lg"
                            onClick={handleAuthClick}
                            disabled={isLoading}
                            className="min-w-48"
                        >
                            <LogIn className="h-4 w-4 mr-2" />
                            Connect to MDRepo
                        </Button>
                    ) : (
                        <Button
                            variant="default"
                            size="lg"
                            onClick={handlePublishClick}
                            disabled={publishExperiment.isPending || isLoading}
                            className="min-w-48"
                        >
                            {publishExperiment.isPending ? (
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            ) : isPublished ? (
                                <Pencil className="h-4 w-4 mr-2" />
                            ) : (
                                <CloudUpload className="h-4 w-4 mr-2" />
                            )}
                            {isPublished ? "View in MDRepo" : "Publish to MDRepo"}
                        </Button>
                    )}

                    {!isPublished && isAuthenticated && (
                        <p className="text-xs text-muted-foreground text-center">
                            After clicking the button, you'll be redirected to MDRepo to complete the metadata and
                            finalize the publication. Your files will be uploaded in the background.
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
};

export default PublishStep;

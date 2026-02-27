import { useState } from "react";

import { Plus, Trash2, Loader2 } from "lucide-react";

import FileSelector from "@/components/FileSelector";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface TprSelectorProps {
    experimentId: string;
    title?: string;
    addTitle: string;
    tprFiles: string[];
    selectedTpr: string | null;
    loading?: boolean;
    onAddTpr: (tpr: string) => void;
    onDeleteTpr: (tpr: string) => void;
    onSelectTpr: (tpr: string) => void;
}

const TprSelector = (props: TprSelectorProps) => {
    const { experimentId, title, addTitle, tprFiles, selectedTpr, loading, onAddTpr, onDeleteTpr, onSelectTpr } = props;

    const [fileSelectorTpr, setFileSelectorTpr] = useState<string>("");

    return (
        <Card className="w-72 shrink-0">
            <CardHeader className="pb-2">{title && <CardTitle className="text-base">{title}</CardTitle>}</CardHeader>
            <CardContent className="flex flex-col gap-3">
                <FileSelector
                    experimentId={experimentId}
                    ext="tpr"
                    title="Select TPR file"
                    onFileSelected={(filePath) => setFileSelectorTpr(filePath.split("/").pop() ?? "")}
                    ignoreFiles={tprFiles}
                />
                <Button
                    variant="default"
                    disabled={!fileSelectorTpr || tprFiles.includes(fileSelectorTpr)}
                    onClick={() => {
                        onAddTpr(fileSelectorTpr);
                        setFileSelectorTpr("");
                    }}
                >
                    <Plus className="h-4 w-4 mr-1" />
                    {addTitle}
                </Button>

                <div className="flex flex-col gap-1">
                    {loading ? (
                        <div className="flex justify-center py-2">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        tprFiles.map((tpr) => (
                            <div
                                key={tpr}
                                className={cn(
                                    "flex items-center justify-between gap-2 px-3 py-2 rounded-md border cursor-pointer transition-colors text-sm",
                                    selectedTpr === tpr
                                        ? "border-foreground bg-primary text-primary-foreground"
                                        : "border-border hover:bg-muted",
                                )}
                                onClick={() => {
                                    if (selectedTpr === tpr) onSelectTpr("");
                                    else onSelectTpr(tpr);
                                }}
                            >
                                <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap" title={tpr}>
                                    {tpr}
                                </span>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    aria-label="delete"
                                    className={cn(
                                        "h-6 w-6 shrink-0",
                                        selectedTpr === tpr
                                            ? "text-primary-foreground hover:bg-primary-foreground/20"
                                            : "",
                                    )}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDeleteTpr(tpr);
                                    }}
                                >
                                    <Trash2 className="h-3 w-3" />
                                </Button>
                            </div>
                        ))
                    )}
                </div>
            </CardContent>
        </Card>
    );
};

export default TprSelector;

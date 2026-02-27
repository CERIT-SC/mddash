import { useState, Fragment } from "react";

import { useDropzone, DropzoneOptions, FileRejection, DropEvent, Accept } from "react-dropzone";
import { CloudUpload, CheckCircle, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { formatFileSize } from "@/util/helpers";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const getAcceptedExtensions = (acceptedTypes: Accept): string =>
    Object.values(acceptedTypes)
        .flat()
        .map((ext: string) => `*${ext}`)
        .join(", ");

interface DropzoneProps extends DropzoneOptions {
    inputName: string;
    className?: string;
    onFilesChange?: (files: File[]) => void;
}

const Dropzone = (props: DropzoneProps) => {
    const { inputName, className, onDrop, onError, onFilesChange, ...dropzoneOptions } = props;

    const [files, setFiles] = useState<File[]>([]);

    const handleDrop = (acceptedFiles: File[], fileRejections: FileRejection[], event: DropEvent) => {
        if (fileRejections.length > 0) {
            toast.error(fileRejections[0].errors[0].message);
        }

        const newFiles = [...files, ...acceptedFiles];
        setFiles(newFiles);
        onDrop?.(acceptedFiles, fileRejections, event);
        onFilesChange?.(newFiles);
    };

    const removeFile = (index: number) => {
        const newFiles = [...files];
        newFiles.splice(index, 1);
        setFiles(newFiles);
        onFilesChange?.(newFiles);
    };

    const handleError = (err: Error) => {
        toast.error(err.message);
        onError?.(err);
    };

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop: handleDrop,
        onError: handleError,
        ...dropzoneOptions,
    });

    const acceptedExtensions = dropzoneOptions.accept ? getAcceptedExtensions(dropzoneOptions.accept) : "";

    return (
        <div className={cn("flex flex-col gap-4", className)}>
            <div
                {...getRootProps()}
                className={cn(
                    "flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-8 text-center text-muted-foreground cursor-pointer transition-colors",
                    isDragActive
                        ? "border-primary bg-primary/10 text-primary"
                        : "hover:border-primary hover:bg-primary/5",
                )}
            >
                <input name={inputName} {...getInputProps()} />
                <CloudUpload className={cn("h-12 w-12", isDragActive ? "text-primary" : "text-muted-foreground")} />
                {isDragActive ? (
                    <p className="text-lg font-medium">Drop the files here...</p>
                ) : (
                    <p className="text-lg font-medium">Drop files here or click.</p>
                )}
                {acceptedExtensions && <p className="text-sm">Accepted file types: {acceptedExtensions}</p>}
            </div>

            {files.length > 0 && (
                <div className="rounded-md border">
                    {files.map((file, index) => (
                        <Fragment key={`${file.name}-${index}`}>
                            <div className="flex items-center gap-3 px-4 py-3">
                                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-500">
                                    <CheckCircle className="h-4 w-4 text-white" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate">{file.name}</p>
                                    <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    aria-label="delete"
                                    onClick={() => removeFile(index)}
                                    className="h-8 w-8 shrink-0"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                            {index < files.length - 1 && <Separator />}
                        </Fragment>
                    ))}
                </div>
            )}
        </div>
    );
};

export default Dropzone;

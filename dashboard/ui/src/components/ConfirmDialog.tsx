import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

interface ConfirmDialogProps {
    open: boolean;
    setOpen: (open: boolean) => void;
    onConfirm?: () => void;
    onCancel?: () => void;
    title?: string;
    message?: string;
    confirmText?: string;
    cancelText?: string;
    confirmColor?: "primary" | "destructive" | "warning";
}

const ConfirmDialog = (props: ConfirmDialogProps) => {
    const {
        open,
        setOpen,
        onConfirm,
        onCancel,
        title = "Confirm Action",
        message = "Are you sure you want to proceed? This action cannot be undone.",
        confirmText = "Confirm",
        cancelText = "Cancel",
        confirmColor = "destructive",
    } = props;

    const handleConfirm = () => {
        onConfirm?.();
        setOpen(false);
    };

    const handleCancel = () => {
        onCancel?.();
        setOpen(false);
    };

    const confirmClass = cn(
        confirmColor === "warning" && "bg-yellow-500 hover:bg-yellow-600 text-white",
        confirmColor === "primary" && "bg-primary hover:bg-primary/90 text-primary-foreground",
    );

    return (
        <AlertDialog open={open} onOpenChange={setOpen}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{title}</AlertDialogTitle>
                    <AlertDialogDescription>{message}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel onClick={handleCancel}>{cancelText}</AlertDialogCancel>
                    <AlertDialogAction onClick={handleConfirm} className={confirmClass || undefined}>
                        {confirmText}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
};

export default ConfirmDialog;

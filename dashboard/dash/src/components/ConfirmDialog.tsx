import { Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Button } from "@mui/material";

interface ConfirmDialogProps {
    open: boolean;
    setOpen: (open: boolean) => void;
    onConfirm?: () => void;
    onCancel?: () => void;
    title?: string;
    message?: string;
    confirmText?: string;
    cancelText?: string;
    confirmColor?: "primary" | "secondary" | "error" | "warning" | "info" | "success";
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
        confirmColor = "error",
    } = props;

    const handleConfirm = () => {
        onConfirm?.();
        setOpen(false);
    };

    const handleCancel = () => {
        onCancel?.();
        setOpen(false);
    };

    return (
        <Dialog open={open} onClose={handleCancel} aria-labelledby="confirm-dialog-title">
            <DialogTitle variant="h4" id="confirm-dialog-title">
                {title}
            </DialogTitle>
            <DialogContent>
                <DialogContentText>{message}</DialogContentText>
            </DialogContent>
            <DialogActions>
                <Button onClick={handleCancel} color="primary">
                    {cancelText}
                </Button>
                <Button onClick={handleConfirm} color={confirmColor} variant="contained">
                    {confirmText}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default ConfirmDialog;

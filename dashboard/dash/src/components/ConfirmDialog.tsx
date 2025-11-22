import { Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Button } from "@mui/material";
import { Check, Close } from "@mui/icons-material";

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
                <Button onClick={handleCancel} color="inherit" variant="outlined" startIcon={<Close />} autoFocus>
                    {cancelText}
                </Button>
                <Button onClick={handleConfirm} color={confirmColor} variant="contained" startIcon={<Check />}>
                    {confirmText}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default ConfirmDialog;

import { Snackbar, Alert, AlertTitle, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { useNotification } from "@/contexts/useNotification";

const NotificationContainer = () => {
    const { notifications, removeNotification } = useNotification();

    return (
        <>
            {notifications.map((notification, index) => (
                <Snackbar
                    key={notification.id}
                    open={true}
                    anchorOrigin={{ vertical: "top", horizontal: "center" }}
                    sx={{
                        top: `${24 + index * 80}px !important`, // Stack notifications vertically
                    }}
                >
                    <Alert
                        severity={notification.severity}
                        variant="filled"
                        sx={{ minWidth: "300px" }}
                        action={
                            <IconButton
                                size="small"
                                aria-label="close"
                                color="inherit"
                                onClick={() => removeNotification(notification.id)}
                            >
                                <CloseIcon fontSize="small" />
                            </IconButton>
                        }
                    >
                        <AlertTitle sx={{ textTransform: "capitalize" }}>{notification.severity}</AlertTitle>
                        {notification.message}
                    </Alert>
                </Snackbar>
            ))}
        </>
    );
};

export default NotificationContainer;

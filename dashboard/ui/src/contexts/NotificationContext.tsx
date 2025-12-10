import React, { useState, useCallback } from "react";
import { NotificationContext, NotificationSeverity, Notification } from "./NotificationTypes";

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [notifications, setNotifications] = useState<Notification[]>([]);

    const removeNotification = useCallback((id: string) => {
        setNotifications((prev) => prev.filter((notification) => notification.id !== id));
    }, []);

    const addNotification = useCallback(
        (message: string, severity: NotificationSeverity = "error") => {
            setNotifications((prev) => {
                const exists = prev.some((n) => n.message === message && n.severity === severity);
                if (exists) return prev;

                const id = `${Date.now()}-${Math.random()}`;
                const notification: Notification = { id, message, severity };

                setTimeout(() => {
                    removeNotification(id);
                }, 5000);

                return [...prev, notification];
            });
        },
        [removeNotification],
    );

    const showError = useCallback(
        (message: string) => {
            addNotification(message, "error");
        },
        [addNotification],
    );

    const showWarning = useCallback(
        (message: string) => {
            addNotification(message, "warning");
        },
        [addNotification],
    );

    const showInfo = useCallback(
        (message: string) => {
            addNotification(message, "info");
        },
        [addNotification],
    );

    const showSuccess = useCallback(
        (message: string) => {
            addNotification(message, "success");
        },
        [addNotification],
    );

    return (
        <NotificationContext.Provider
            value={{
                notifications,
                addNotification,
                removeNotification,
                showError,
                showWarning,
                showInfo,
                showSuccess,
            }}
        >
            {children}
        </NotificationContext.Provider>
    );
};

import React, { createContext, useContext, useState, useCallback } from "react";

export type NotificationSeverity = "error" | "warning" | "info" | "success";

export interface Notification {
    id: string;
    message: string;
    severity: NotificationSeverity;
}

interface NotificationContextType {
    notifications: Notification[];
    addNotification: (message: string, severity?: NotificationSeverity) => void;
    removeNotification: (id: string) => void;
    showError: (message: string) => void;
    showWarning: (message: string) => void;
    showInfo: (message: string) => void;
    showSuccess: (message: string) => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [notifications, setNotifications] = useState<Notification[]>([]);

    const addNotification = useCallback((message: string, severity: NotificationSeverity = "error") => {
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
    }, []);

    const removeNotification = useCallback((id: string) => {
        setNotifications((prev) => prev.filter((notification) => notification.id !== id));
    }, []);

    const showError = useCallback(
        (message: string) => {
            addNotification(message, "error");
        },
        [addNotification]
    );

    const showWarning = useCallback(
        (message: string) => {
            addNotification(message, "warning");
        },
        [addNotification]
    );

    const showInfo = useCallback(
        (message: string) => {
            addNotification(message, "info");
        },
        [addNotification]
    );

    const showSuccess = useCallback(
        (message: string) => {
            addNotification(message, "success");
        },
        [addNotification]
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

export const useNotification = (): NotificationContextType => {
    const context = useContext(NotificationContext);
    if (!context) {
        throw new Error("useNotification must be used within a NotificationProvider");
    }
    return context;
};

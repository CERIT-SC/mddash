import { createContext } from "react";

export type NotificationSeverity = "error" | "warning" | "info" | "success";

export interface Notification {
    id: string;
    message: string;
    severity: NotificationSeverity;
}

export interface NotificationContextType {
    notifications: Notification[];
    addNotification: (message: string, severity?: NotificationSeverity) => void;
    removeNotification: (id: string) => void;
    showError: (message: string) => void;
    showWarning: (message: string) => void;
    showInfo: (message: string) => void;
    showSuccess: (message: string) => void;
}

export const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

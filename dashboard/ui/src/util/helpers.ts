/**
 * Convert seconds to a human-readable duration string.
 *
 * @param seconds number of seconds
 * @returns human-readable duration string
 */
export function formatDuration(seconds: number): string {
    if (seconds == null || isNaN(seconds)) return "?";
    const units = [
        { label: "day", secs: 86400 },
        { label: "hour", secs: 3600 },
        { label: "minute", secs: 60 },
        { label: "second", secs: 1 },
    ];
    let remaining = Math.max(0, Math.floor(seconds));
    const parts: string[] = [];
    for (const { label, secs } of units) {
        if (remaining >= secs) {
            const value = Math.floor(remaining / secs);
            parts.push(`${value} ${label}${value !== 1 ? "s" : ""}`);
            remaining -= value * secs;
        }
        // Only show up to 3 largest units for brevity
        if (parts.length === 3) break;
    }
    return parts.length ? parts.join(", ") : "0 seconds";
}

/**
 * Formats bytes as human-readable text with units.
 *
 * @param bytes number of bytes
 * @returns formatted string (e.g., "1.5 MB")
 */
export const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${units[i]}`;
};

/**
 * Format ISO datetime string to human-readable format using user's locale.
 *
 * @param isoString ISO 8601 datetime string
 * @returns formatted datetime string based on user's locale
 */
export const formatDateTime = (isoString: string): string => {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
};

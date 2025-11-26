import React, { createContext, useMemo, useState, useCallback, ReactNode } from "react";
import {
    createTheme,
    ThemeOptions,
    responsiveFontSizes,
    ThemeProvider as MuiThemeProvider,
    CssBaseline,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import type { CSSObject, Theme } from "@mui/material/styles";
import { TypographyOptions } from "@mui/material/styles/createTypography";

const typography: TypographyOptions = {
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    // Large (32px) - For main headings and titles
    h1: { fontSize: "32px", fontWeight: "bold", padding: "12px 0px" },
    h2: { fontSize: "32px", fontWeight: "normal", padding: "8px 0px" },

    // Medium (20px) - For section headings
    h3: { fontSize: "20px", fontWeight: "bold", padding: "8px 0px" },
    h4: { fontSize: "20px", fontWeight: "normal", padding: "4px 0px" },
    h5: { fontSize: "20px", fontWeight: "normal", padding: "4px 0px" },
    h6: { fontSize: "20px", fontWeight: "normal", padding: "4px 0px" },

    // Regular (16px) - For body text and most content
    body1: { fontSize: "16px", fontWeight: "normal" },
    subtitle1: { fontSize: "16px", fontWeight: "bold" },
    button: { fontSize: "16px", fontWeight: "normal", textTransform: "none" },

    // Small (12px) - For captions, labels, secondary info
    body2: { fontSize: "12px", fontWeight: "normal" },
    subtitle2: { fontSize: "12px", fontWeight: "bold" },
    caption: { fontSize: "12px", fontWeight: "normal" },
    overline: { fontSize: "12px", fontWeight: "bold", textTransform: "uppercase" },
};

const lightThemeOptions: ThemeOptions = {
    palette: {
        mode: "light",
        primary: { main: "#1E40AF" },
        secondary: { main: "#f37726" },
        error: { main: "#f44336" },
        warning: { main: "#ff9800" },
        info: { main: "#2196f3" },
        success: { main: "#4caf50" },
    },
    typography,
};

const darkThemeOptions: ThemeOptions = {
    palette: {
        mode: "dark",
        primary: { main: "#1E40AF" },
        secondary: { main: "#f37726" },
        error: { main: "#f44336" },
        warning: { main: "#ff9800" },
        info: { main: "#2196f3" },
        success: { main: "#4caf50" },
        background: { default: "#212529", paper: "#2b3035" },
    },
    typography,
};

const createScrollbarOverrides = (palette: Theme["palette"]): CSSObject => {
    const thumbColor = palette.mode === "light" 
        ? alpha(palette.grey[500], 0.4)
        : alpha(palette.grey[400], 0.3);
    const thumbHoverColor = palette.mode === "light"
        ? alpha(palette.grey[700], 0.7)
        : alpha(palette.grey[300], 0.6);
    const trackHoverColor = palette.mode === "light"
        ? alpha(palette.grey[300], 0.15)
        : alpha(palette.grey[700], 0.15);

    return {
        "*::-webkit-scrollbar": {
            width: "14px",
            height: "14px",
        },
        "*::-webkit-scrollbar-track": {
            background: "transparent",
        },
        "*::-webkit-scrollbar-track:hover": {
            background: trackHoverColor,
        },
        "*::-webkit-scrollbar-thumb": {
            background: thumbColor,
            borderRadius: "7px",
            border: "3px solid transparent",
            backgroundClip: "padding-box",
            transition: "background 0.2s ease",
        },
        "*::-webkit-scrollbar-thumb:hover": {
            background: thumbHoverColor,
        },
        "*": {
            scrollbarWidth: "thin",
            scrollbarColor: `${thumbColor} transparent`,
        },
    };
};

export const ThemeContext = createContext({
    mode: "light",
    toggleTheme: () => {},
});

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
    // Get initial mode: localStorage > system preference > default 'light'
    const getInitialMode = () => {
        if (typeof window === "undefined") return "light";
        const stored = localStorage.getItem("themeMode");
        if (stored === "light" || stored === "dark") return stored;
        if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
        return "light";
    };

    const [mode, setMode] = useState<"light" | "dark">(getInitialMode);

    // Save mode to localStorage when it changes
    React.useEffect(() => {
        localStorage.setItem("themeMode", mode);
    }, [mode]);

    const toggleTheme = useCallback(() => setMode((m) => (m === "light" ? "dark" : "light")), []);
    const theme = useMemo(() => {
        const base = createTheme(mode === "light" ? lightThemeOptions : darkThemeOptions);

        base.components = {
            ...base.components,
            MuiCssBaseline: {
                styleOverrides: createScrollbarOverrides(base.palette),
            },
        };

        return responsiveFontSizes(base);
    }, [mode]);
    return (
        <ThemeContext.Provider value={{ mode, toggleTheme }}>
            <MuiThemeProvider theme={theme}>
                <CssBaseline />
                {children}
            </MuiThemeProvider>
        </ThemeContext.Provider>
    );
};

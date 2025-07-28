import React, { createContext, useMemo, useState, useCallback, ReactNode } from "react";
import {
    createTheme,
    ThemeOptions,
    responsiveFontSizes,
    ThemeProvider as MuiThemeProvider,
    CssBaseline,
} from "@mui/material";

const lightThemeOptions: ThemeOptions = {
    palette: {
        mode: "light",
        primary: { main: "#1E3A8A" },
        secondary: { main: "#f37726" },
        error: { main: "#f44336" },
        warning: { main: "#ff9800" },
        info: { main: "#2196f3" },
        success: { main: "#4caf50" },
    },
    typography: {
        fontFamily: "Verdana",
        h1: { fontSize: "40px", fontWeight: "bold", padding: "25px 0px" },
        h2: { fontSize: "36px", fontWeight: "bold", padding: "10px 0px" },
        h3: { fontSize: "30px", fontWeight: "bold", padding: "10px 0px" },
        h4: { fontSize: "24px", fontWeight: "bold", padding: "10px 0px" },
    },
};

const darkThemeOptions: ThemeOptions = {
    palette: {
        mode: "dark",
        primary: { main: "#2c7bb6" },
        secondary: { main: "#f37726" },
        error: { main: "#f44336" },
        warning: { main: "#ff9800" },
        info: { main: "#2196f3" },
        success: { main: "#4caf50" },
        background: { default: "#212529", paper: "#2b3035" },
    },
    typography: {
        fontFamily: "Verdana",
        h1: { fontSize: "40px", fontWeight: "bold", padding: "25px 0px" },
        h2: { fontSize: "36px", fontWeight: "bold", padding: "10px 0px" },
        h3: { fontSize: "30px", fontWeight: "bold", padding: "10px 0px" },
        h4: { fontSize: "24px", fontWeight: "bold", padding: "10px 0px" },
    },
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

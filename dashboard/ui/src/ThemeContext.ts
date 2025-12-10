import { createContext } from "react";

export interface ThemeContextType {
    mode: string;
    toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextType>({
    mode: "light",
    toggleTheme: () => {},
});

import { useContext } from "react";
import { ThemeContext } from "./ThemeContext";

export const useThemeMode = () => useContext(ThemeContext);

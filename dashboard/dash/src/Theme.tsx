import { createTheme, ThemeOptions, responsiveFontSizes } from '@mui/material';

const themeOptions: ThemeOptions = {
    palette: {
        primary: {
            main: '#1E3A8A',
        },
        secondary: {
            main: '#F59E0B',
        },
        error: {
            main: '#f44336',
        },
        warning: {
            main: '#ff9800',
        },
        info: {
            main: '#2196f3',
        },
        success: {
            main: '#4caf50',
        },
    },
    typography: {
        fontFamily: 'Verdana',
        h1: {
            fontSize: '40px',
            fontWeight: 'bold',
            padding: '25px 0px',
        },
        h2: {
            fontSize: '36px',
            fontWeight: 'bold',
            padding: '10px 0px',
        },
        h3: {
            fontSize: '30px',
            fontWeight: 'bold',
            padding: '10px 0px',
        },
        h4: {
            fontSize: '24px',
            fontWeight: 'bold',
            padding: '10px 0px',
        }
    },
};


const baseTheme = createTheme(themeOptions);
export const theme = responsiveFontSizes(baseTheme);

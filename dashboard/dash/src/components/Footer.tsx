import { useTheme, Typography, Link } from '@mui/material'


const Footer = () => {
    const theme = useTheme();

    return (
        <footer style={{ backgroundColor: theme.palette.primary.main }}>
            <Typography variant="caption">TODO</Typography>
        </footer>
    )
}

export default Footer

import { useTheme, Typography, Link } from '@mui/material'


const Footer = () => {
    const theme = useTheme();

    return (
        <footer style={{ backgroundColor: theme.palette.primary.main }}>
            <Typography variant="caption">Made with ❤️ by <Link color='secondary' href="https://disa.fi.muni.cz/complex-data-analysis/home">Intelligent Systems for Complex Data Research Group</Link></Typography>
        </footer>
    )
}

export default Footer

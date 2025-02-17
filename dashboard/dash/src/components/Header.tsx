import { Typography, useTheme } from '@mui/material'
import { Link } from 'react-router-dom';
import { BASE_PATH } from '../util/const';

const Header = () => {
    const theme = useTheme();

    return (
        <header style={{ backgroundColor: theme.palette.primary.main }}>
            <Link to={BASE_PATH} style={{ textDecoration: 'none', color: 'white' }}>
                <Typography variant="h1">FAIR MD Dash</Typography>
            </Link>
        </header>
    )
}

export default Header

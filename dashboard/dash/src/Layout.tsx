import { Outlet } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'

import Header from './components/Header'
import Footer from './components/Footer'
import { theme } from './Theme'


const Layout = () => {
    return (
        <ThemeProvider theme={theme}>
            <Header />
            <main>
                <Outlet />
            </main>
            <Footer />
        </ThemeProvider>
    )
}

export default Layout

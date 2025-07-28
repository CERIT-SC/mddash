import { Outlet } from "react-router-dom";

import Header from "./components/Header";
import Footer from "./components/Footer";
import { ThemeProvider } from "./Theme";

const Layout = () => {
    return (
        <ThemeProvider>
            <Header />
            <main>
                <Outlet />
            </main>
            <Footer />
        </ThemeProvider>
    );
};

export default Layout;

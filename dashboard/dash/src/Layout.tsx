import { Outlet } from "react-router-dom";

import Header from "./components/Header";
import Footer from "./components/Footer";
import { ThemeProvider } from "./Theme";
import { NotificationProvider } from "./contexts/NotificationContext";
import NotificationContainer from "./components/NotificationContainer";

const Layout = () => {
    return (
        <ThemeProvider>
            <NotificationProvider>
                <Header />
                <main>
                    <Outlet />
                </main>
                <Footer />
                <NotificationContainer />
            </NotificationProvider>
        </ThemeProvider>
    );
};

export default Layout;

import { Outlet } from "@tanstack/react-router";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const RootLayout = () => {
    return (
        <TooltipProvider>
            <Header />
            <main className="min-h-[90vh] px-12 py-12">
                <Outlet />
            </main>
            <Footer />
            <Toaster position="top-center" richColors closeButton />
        </TooltipProvider>
    );
};

export default RootLayout;

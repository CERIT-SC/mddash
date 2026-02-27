import { Outlet } from "@tanstack/react-router"

import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import Footer from "@/components/Footer"
import Header from "@/components/Header"

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
  )
}

export default RootLayout

import { Outlet } from "@tanstack/react-router"

import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import Footer from "@/components/Footer"
import Header from "@/components/Header"

const RootLayout = () => {
  return (
    <TooltipProvider>
      <div className="flex min-h-screen flex-col">
        <Header />
        <main className="flex-1 px-12 py-12">
          <Outlet />
        </main>
        <Footer />
      </div>
      <Toaster position="top-center" richColors closeButton />
    </TooltipProvider>
  )
}

export default RootLayout

import { Link } from "@tanstack/react-router"
import { Frown } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const NotFound = () => {
  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <Card className="max-w-md p-6 text-center">
        <CardContent className="flex flex-col items-center gap-4 pt-2">
          <Frown className="text-muted-foreground h-20 w-20" />
          <h1 className="text-5xl font-bold">404</h1>
          <h2 className="text-xl font-semibold">Oops! This page wandered off...</h2>
          <p className="text-muted-foreground text-sm">
            Looks like the page you're looking for got lost in cyberspace — maybe it's off chasing butterflies, or just
            hiding from you!
          </p>
          <Button asChild>
            <Link to="/">Take me home!</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

export default NotFound

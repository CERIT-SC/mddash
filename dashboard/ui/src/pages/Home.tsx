import Experiments from "@/components/Experiments"
import Metrics from "@/components/Metrics"

const Home = () => {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-3xl font-bold">My Experiments</h1>

      <Experiments />

      <h1 className="text-3xl font-bold">Resource Usage</h1>

      <Metrics />

      <h1 className="text-3xl font-bold">Documentation</h1>

      <p className="text-muted-foreground px-4">There is no documentation yet :P</p>
    </div>
  )
}

export default Home

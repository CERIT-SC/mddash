import { useState } from "react"

export default function App() {
  const [count, setCount] = useState(0)

  return (
    <div style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>MDDash</h1>
      <p>Landing page placeholder.</p>
      <button onClick={() => setCount((c) => c + 1)}>
        Count: {count}
      </button>
      <br />
      <br />
      <a href="/hub/">Go to Hub →</a>
    </div>
  )
}

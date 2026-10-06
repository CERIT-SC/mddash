import { useEffect, useRef, useState } from "react"

interface ProgressEvent {
  progress?: number
  message?: string
  html_message?: string
  ready?: boolean
  failed?: boolean
}

export interface LogEntry {
  text: string
  html?: string
}

export type ProgressStatus = "connecting" | "streaming" | "ready" | "failed"

// Hub 400s progress requests that land during spawn-failure cleanup; reconnecting replays
// the terminal failed event. Budget counts consecutive failed connects (reset on open).
const MAX_CONNECT_FAILURES = 5
const RETRY_BASE_DELAY_MS = 1000

export function useSpawnProgress(progressUrl: string) {
  const [progress, setProgress] = useState(0)
  const [currentMessage, setCurrentMessage] = useState<string | null>(null)
  const [log, setLog] = useState<LogEntry[]>([])
  const [status, setStatus] = useState<ProgressStatus>("connecting")
  const [streamEnded, setStreamEnded] = useState(false)

  const logRef = useRef<LogEntry[]>([])
  const pushLog = (entry: LogEntry) => {
    logRef.current = [...logRef.current, entry]
    setLog(logRef.current)
  }

  useEffect(() => {
    let source: EventSource | null = null
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let connectFailures = 0
    let disposed = false

    const connect = () => {
      if (disposed) return
      const es = new EventSource(progressUrl)
      source = es

      es.onopen = () => {
        connectFailures = 0
      }

      es.onmessage = (event: MessageEvent<string>) => {
        if (disposed) return
        setStatus("streaming")
        const evt: ProgressEvent = JSON.parse(event.data)
        if (evt.progress !== undefined) setProgress(evt.progress)
        if (evt.html_message !== undefined) {
          setCurrentMessage(evt.html_message.replace(/<[^>]*>/g, ""))
          pushLog({ text: evt.html_message.replace(/<[^>]*>/g, ""), html: evt.html_message })
        } else if (evt.message !== undefined) {
          setCurrentMessage(evt.message)
          pushLog({ text: evt.message })
        }
        if (evt.ready) {
          setStatus("ready")
          es.close()
          window.location.reload()
        } else if (evt.failed) {
          setStatus("failed")
          es.close()
        }
      }

      es.onerror = () => {
        es.close()
        if (disposed) return
        connectFailures += 1
        if (connectFailures >= MAX_CONNECT_FAILURES) {
          setStreamEnded(true)
          return
        }
        retryTimer = setTimeout(connect, RETRY_BASE_DELAY_MS * connectFailures)
      }
    }

    connect()

    return () => {
      disposed = true
      if (retryTimer !== undefined) clearTimeout(retryTimer)
      source?.close()
    }
  }, [progressUrl])

  return { progress, currentMessage, log, status, streamEnded }
}

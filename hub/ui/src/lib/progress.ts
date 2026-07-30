import { useEffect, useRef, useState } from "react"

export interface ProgressEvent {
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
    const source = new EventSource(progressUrl)

    source.onmessage = (event: MessageEvent<string>) => {
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
        source.close()
        window.location.reload()
      } else if (evt.failed) {
        setStatus("failed")
        source.close()
      }
    }

    source.onerror = () => {
      source.close()
      setStreamEnded(true)
    }

    return () => {
      source.close()
    }
  }, [progressUrl])

  return { progress, currentMessage, log, status, streamEnded }
}

import { useEffect, useRef, useState } from "react"

/**
 * Spawn progress events from the hub's progress API (SSE).
 * Mirrors the stock spawn_pending.html behavior, plus bounded reconnect with
 * exponential backoff instead of silently dying on the first stream error.
 */

export interface ProgressEvent {
  progress?: number
  message?: string
  html_message?: string
  ready?: boolean
  failed?: boolean
  url?: string
}

export interface LogEntry {
  text: string
  html?: string
}

export type ProgressStatus = "connecting" | "streaming" | "reconnecting" | "ready" | "failed" | "lost"

const MAX_RECONNECTS = 12
const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 10000

export function useSpawnProgress(progressUrl: string) {
  const [progress, setProgress] = useState(0)
  const [currentMessage, setCurrentMessage] = useState<string | null>(null)
  const [log, setLog] = useState<LogEntry[]>([])
  const [status, setStatus] = useState<ProgressStatus>("connecting")

  // Mutable snapshot for callbacks (avoids stale closures across reconnects).
  const logRef = useRef<LogEntry[]>([])
  const pushLog = (entry: LogEntry) => {
    logRef.current = [...logRef.current, entry]
    setLog(logRef.current)
  }

  useEffect(() => {
    let attempts = 0
    let source: EventSource | null = null
    let timer: ReturnType<typeof setTimeout> | null = null
    let done = false

    const nextDelay = () => Math.min(BASE_DELAY_MS * 1.5 ** attempts, MAX_DELAY_MS)

    const connect = () => {
      if (done) return
      source = new EventSource(progressUrl)

      source.onmessage = (event: MessageEvent<string>) => {
        attempts = 0
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
          source?.close()
          // Reload: once the server is ready, the hub redirects this page to it.
          window.location.reload()
        } else if (evt.failed) {
          setStatus("failed")
          source?.close()
        }
      }

      source.onerror = () => {
        source?.close()
        if (done) return
        if (attempts >= MAX_RECONNECTS) {
          setStatus("lost")
          return
        }
        setStatus("reconnecting")
        const delay = nextDelay()
        attempts += 1
        timer = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      done = true
      source?.close()
      if (timer) clearTimeout(timer)
    }
  }, [progressUrl])

  return { progress, currentMessage, log, status }
}

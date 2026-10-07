import * as React from 'react'

import { api, type RunCounters } from '@/lib/api'

/** Subscribes to /runs/{id}/stream via SSE with auto-reconnect. */
export function useRunStream(runId: string | null) {
  const [data, setData] = React.useState<RunCounters | null>(null)
  const [connected, setConnected] = React.useState(false)

  React.useEffect(() => {
    if (!runId) return

    let cancelled = false
    let source: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      if (cancelled) return
      source = new EventSource(api.streamUrl(runId!))

      source.addEventListener('counters', (event) => {
        setConnected(true)
        try {
          setData(JSON.parse((event as MessageEvent).data))
        } catch {
          // ignore malformed payloads
        }
      })

      source.onerror = () => {
        setConnected(false)
        source?.close()
        if (!cancelled) reconnectTimer = setTimeout(connect, 2000)
      }
    }

    connect()

    return () => {
      cancelled = true
      source?.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [runId])

  return { data, connected }
}

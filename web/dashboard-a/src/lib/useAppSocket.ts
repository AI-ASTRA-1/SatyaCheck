import { useEffect, useRef, useState } from 'react'
import type { AppMessage } from '../types/risk'

export type ConnectionState = 'connecting' | 'open' | 'closed' | 'error'

interface UseAppSocketResult {
  connectionState: ConnectionState
  latest: AppMessage | null
  history: AppMessage[]
  lastMessageAt: number | null
}

const HISTORY_LIMIT = 200

/**
 * Connects to the fake local WebSocket only (never a real backend). No
 * auto-reconnect: a closed connection stays closed and visibly disconnected,
 * which is what the required self-check (kill the mock server, see a clear
 * disconnected state) exercises.
 */
export function useAppSocket(url: string): UseAppSocketResult {
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting')
  const [latest, setLatest] = useState<AppMessage | null>(null)
  const [history, setHistory] = useState<AppMessage[]>([])
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let cancelled = false
    setConnectionState('connecting')

    const socket = new WebSocket(url)
    socketRef.current = socket

    socket.addEventListener('open', () => {
      if (!cancelled) setConnectionState('open')
    })

    socket.addEventListener('message', (event) => {
      if (cancelled) return
      try {
        const message = JSON.parse(event.data as string) as AppMessage
        setLatest(message)
        setLastMessageAt(Date.now())
        setHistory((prev) => [message, ...prev].slice(0, HISTORY_LIMIT))
      } catch {
        // Malformed message: ignored, connection state is unaffected.
      }
    })

    socket.addEventListener('close', () => {
      if (!cancelled) setConnectionState('closed')
    })

    socket.addEventListener('error', () => {
      if (!cancelled) setConnectionState('error')
    })

    return () => {
      cancelled = true
      socket.close()
    }
  }, [url])

  return { connectionState, latest, history, lastMessageAt }
}

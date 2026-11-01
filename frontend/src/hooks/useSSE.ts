/**
 * AGGRIX MTA Layer — React Server-Sent Events (SSE) Hook
 *
 * Establishes an authenticated EventSource connection to:
 * GET /api/v1/analytics/stream?tenant_id=...&token=...
 *
 * Features:
 * - Automatic authentication token injection from localStorage
 * - Strict tenant-scoped event filtering
 * - Reconnection support with Last-Event-ID
 * - Live event history buffer
 * - Automatic cleanup on unmount or tenant switch
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import { env } from '../config/env'
import { getStoredToken } from '../services/authService'
import type { BroadcastEvent } from '../types/api'

export interface UseSSEOptions {
  tenantId?: string | null
  enabled?: boolean
  maxEventsHistory?: number
  onEvent?: (event: BroadcastEvent) => void
}

export interface UseSSEResult {
  isConnected: boolean
  lastEvent: BroadcastEvent | null
  events: BroadcastEvent[]
  error: string | null
  reconnect: () => void
}

export function useSSE(options: UseSSEOptions = {}): UseSSEResult {
  const {
    tenantId,
    enabled = true,
    maxEventsHistory = 20,
    onEvent,
  } = options

  const [isConnected, setIsConnected] = useState<boolean>(false)
  const [lastEvent, setLastEvent] = useState<BroadcastEvent | null>(null)
  const [events, setEvents] = useState<BroadcastEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(() => {
    // If not enabled or in server environment, skip
    if (!enabled || typeof window === 'undefined' || typeof EventSource === 'undefined') {
      return
    }

    // Clean up any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }

    const token = getStoredToken()
    const queryParams = new URLSearchParams()

    if (tenantId) {
      queryParams.append('tenant_id', tenantId)
    }
    if (token) {
      queryParams.append('token', token)
    }

    const queryString = queryParams.toString()
    const sseUrl = `${env.apiBaseUrl}/api/v1/analytics/stream${queryString ? `?${queryString}` : ''}`

    try {
      const es = new EventSource(sseUrl)
      eventSourceRef.current = es

      es.onopen = () => {
        setIsConnected(true)
        setError(null)
      }

      es.onmessage = (messageEvent: MessageEvent) => {
        try {
          // Heartbeats or comments may arrive
          if (!messageEvent.data || messageEvent.data === 'ping') {
            return
          }

          const parsed: BroadcastEvent = JSON.parse(messageEvent.data)
          setLastEvent(parsed)
          setEvents(prev => [parsed, ...prev].slice(0, maxEventsHistory))

          if (onEventRef.current) {
            onEventRef.current(parsed)
          }
        } catch {
          // Non-JSON frames (e.g. heartbeat pings) safely ignored
        }
      }

      es.onerror = () => {
        setIsConnected(false)
        setError('Stream connection dropped. Reconnecting...')
      }
    } catch (err: unknown) {
      setIsConnected(false)
      setError(err instanceof Error ? err.message : 'Failed to establish event stream')
    }
  }, [enabled, tenantId, maxEventsHistory])

  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setIsConnected(false)
    }
  }, [connect])

  const reconnect = useCallback(() => {
    connect()
  }, [connect])

  return {
    isConnected,
    lastEvent,
    events,
    error,
    reconnect,
  }
}

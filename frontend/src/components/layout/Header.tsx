import React, { useEffect, useState } from 'react'
import { Menu, Globe, Server, ShieldAlert } from 'lucide-react'
import { env } from '../../config/env'
import { fetchHealth } from '../../services/api'
import type { HealthResponse } from '../../types/api'

interface HeaderProps {
  onToggleSidebar: () => void
  isSidebarOpen?: boolean
}

export const Header: React.FC<HeaderProps> = ({ onToggleSidebar, isSidebarOpen = false }) => {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    let isMounted = true
    const checkConnection = async () => {
      try {
        const data = await fetchHealth()
        if (isMounted) setHealth(data)
      } catch {
        if (isMounted) {
          setHealth({
            status: 'unhealthy',
            database: 'disconnected',
            environment: env.appEnv,
            error: 'Backend unreachable',
          })
        }
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    checkConnection()
    const interval = setInterval(checkConnection, 15000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  return (
    <header className="app-header" role="banner">
      <div className="header-left">
        <button
          className="menu-trigger"
          onClick={onToggleSidebar}
          aria-label={isSidebarOpen ? 'Close navigation sidebar' : 'Open navigation sidebar'}
          aria-expanded={isSidebarOpen}
          aria-controls="app-sidebar"
        >
          <Menu size={20} aria-hidden="true" />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)' }}>
          <Server size={14} aria-hidden="true" />
          <span>Backend:</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }} title={env.apiBaseUrl}>
            {env.apiBaseUrl}
          </span>
        </div>
      </div>

      <div className="header-right">
        {loading ? (
          <span className="badge badge-neutral" role="status" aria-live="polite">
            Probing backend...
          </span>
        ) : health?.status === 'healthy' ? (
          <span className="badge badge-success" role="status" aria-live="polite">
            <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: 'var(--success)', display: 'inline-block' }} aria-hidden="true" />
            FastAPI Connected (DB: {health.database})
          </span>
        ) : (
          <span className="badge badge-warning" role="status" aria-live="polite" title={health?.error || 'Backend not responding'}>
            <ShieldAlert size={12} aria-hidden="true" />
            FastAPI Offline (Port 8000)
          </span>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', fontSize: 12 }}>
          <Globe size={13} style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
          <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{env.appEnv}</span>
        </div>
      </div>
    </header>
  )
}

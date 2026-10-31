import React, { useEffect, useState } from 'react'
import { Menu, Globe, Server, ShieldAlert } from 'lucide-react'
import { env } from '../../config/env'
import { fetchHealth } from '../../services/api'
import type { HealthResponse } from '../../types/api'

interface HeaderProps {
  onToggleSidebar: () => void
}

export const Header: React.FC<HeaderProps> = ({ onToggleSidebar }) => {
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
    <header className="app-header">
      <div className="header-left">
        <button
          className="menu-trigger"
          onClick={onToggleSidebar}
          aria-label="Open sidebar"
        >
          <Menu size={20} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)' }}>
          <Server size={14} />
          <span>Backend Target:</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{env.apiBaseUrl}</span>
        </div>
      </div>

      <div className="header-right">
        {loading ? (
          <span className="badge badge-neutral">Checking backend...</span>
        ) : health?.status === 'healthy' ? (
          <span className="badge badge-success">
            <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: 'var(--success)', display: 'inline-block' }} />
            FastAPI Connected (DB: {health.database})
          </span>
        ) : (
          <span className="badge badge-warning" title={health?.error || 'Backend not responding'}>
            <ShieldAlert size={12} />
            FastAPI Offline (Start Backend on :8000)
          </span>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', borderRadius: 'var(--radius-sm)', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)', fontSize: 12 }}>
          <Globe size={13} style={{ color: 'var(--accent-primary)' }} />
          <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{env.appEnv}</span>
        </div>
      </div>
    </header>
  )
}


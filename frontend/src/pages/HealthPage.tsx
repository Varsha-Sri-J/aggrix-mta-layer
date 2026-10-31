import React, { useState, useEffect } from 'react'
import { Activity, RefreshCw, CheckCircle2, XCircle, Server } from 'lucide-react'
import { Card } from '../components/common/Card'
import { StatusBadge } from '../components/common/StatusBadge'
import { env } from '../config/env'
import { fetchHealth, fetchRootMeta } from '../services/api'
import type { HealthResponse, RootMetaResponse } from '../types/api'

export const HealthPage: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [rootMeta, setRootMeta] = useState<RootMetaResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [lastCheck, setLastCheck] = useState<string>('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const runDiagnostics = async () => {
    setLoading(true)
    setErrorMsg(null)
    try {
      const [metaData, healthData] = await Promise.all([
        fetchRootMeta().catch(err => {
          console.warn('Root meta error:', err)
          return null
        }),
        fetchHealth().catch(err => {
          console.warn('Health error:', err)
          return null
        }),
      ])
      setRootMeta(metaData)
      setHealth(healthData)
      setLastCheck(new Date().toLocaleTimeString())
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Unknown diagnostic error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    runDiagnostics()
  }, [])

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">
            <Activity size={26} style={{ color: 'var(--accent-primary)' }} />
            System Health & Diagnostics
          </h1>
          <p className="page-description">
            Live health verification against active FastAPI service and PostgreSQL connection pool
          </p>
        </div>
        <button
          onClick={runDiagnostics}
          disabled={loading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            backgroundColor: 'var(--accent-primary)',
            color: '#ffffff',
            padding: '8px 16px',
            borderRadius: 'var(--radius-sm)',
            fontWeight: 600,
            fontSize: 13,
            opacity: loading ? 0.7 : 1,
          }}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Probing...' : 'Run Diagnostic Probe'}
        </button>
      </div>

      {lastCheck && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
          Last probe completed at: <strong style={{ color: 'var(--text-secondary)' }}>{lastCheck}</strong>
        </div>
      )}

      {errorMsg && (
        <div style={{
          backgroundColor: 'var(--danger-bg)',
          border: '1px solid var(--danger-border)',
          borderRadius: 'var(--radius-md)',
          padding: 16,
          marginBottom: 20,
          color: 'var(--danger)',
          fontSize: 13,
        }}>
          <strong>Diagnostic Failure:</strong> {errorMsg}
        </div>
      )}

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <Card title={<><Server size={18} /> Endpoint: GET / (Root Metadata)</>}>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-muted)' }}>Response Status:</span>
              {rootMeta ? (
                <span className="badge badge-success"><CheckCircle2 size={12} /> HTTP 200 OK</span>
              ) : (
                <span className="badge badge-danger"><XCircle size={12} /> Unreachable</span>
              )}
            </div>
            <div className="code-box">
              {rootMeta ? JSON.stringify(rootMeta, null, 2) : 'No response from root endpoint. Verify FastAPI is listening on ' + env.apiBaseUrl}
            </div>
          </div>
        </Card>

        <Card title={<><Activity size={18} /> Endpoint: GET /api/v1/health (DB Check)</>}>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-muted)' }}>Database Check (SELECT 1):</span>
              <StatusBadge status={health?.database === 'connected' ? 'healthy' : 'unhealthy'} label={health?.database?.toUpperCase() || 'DISCONNECTED'} />
            </div>
            <div className="code-box">
              {health ? JSON.stringify(health, null, 2) : 'No response from health endpoint.'}
            </div>
          </div>
        </Card>
      </div>

      <Card title="FastAPI Health Check Architecture">
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <p>The health endpoint executes <code style={{ color: '#38bdf8' }}>SELECT 1</code> through SQLAlchemy session dependency (<code style={{ color: '#38bdf8' }}>get_db</code>). When PostgreSQL is reachable, it responds with HTTP 200 and <code style={{ color: '#38bdf8' }}>database: "connected"</code>. If the database connection drops, it intercepts the exception and returns HTTP 503 Service Unavailable with the discrete error payload.</p>
        </div>
      </Card>
    </div>
  )
}


import React, { useState } from 'react'
import { LogIn, ShieldAlert, KeyRound, Server, AlertCircle, ArrowRight } from 'lucide-react'
import { Card } from '../components/common/Card'
import { StatusBadge } from '../components/common/StatusBadge'
import { authService, AUTH_AWAITING_MESSAGE } from '../services/authService'
import { env } from '../config/env'

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState<string>('')
  const [password, setPassword] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [resultMessage, setResultMessage] = useState<{ type: 'error' | 'info'; text: string } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResultMessage(null)

    try {
      // Connects directly to the real endpoint POST /api/v1/auth/login
      await authService.login({ username, password })
      setResultMessage({
        type: 'info',
        text: 'Login succeeded. JWT token stored.',
      })
    } catch (err: unknown) {
      setResultMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Authentication failed',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <div className="page-header">
        <h1 className="page-title">
          <KeyRound size={26} style={{ color: 'var(--accent-primary)' }} />
          Authentication & RBAC Readiness
        </h1>
        <p className="page-description">
          FastAPI authentication abstraction and token readiness for merchant and manager roles
        </p>
      </div>

      {/* Prominent Architectural Banner */}
      <div style={{
        backgroundColor: 'rgba(245, 158, 11, 0.08)',
        border: '1px solid rgba(245, 158, 11, 0.25)',
        borderRadius: 'var(--radius-md)',
        padding: '18px 22px',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 14,
      }}>
        <ShieldAlert size={22} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 2 }} />
        <div>
          <div style={{ fontWeight: 700, color: '#ffffff', fontSize: 14, marginBottom: 4 }}>
            Authentication Awaiting Stage 4 Backend Implementation
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
            {AUTH_AWAITING_MESSAGE}
            <br />
            <strong>Accuracy Guarantee:</strong> No fake JWTs, dummy accounts, or simulated user sessions are generated. The form below connects directly to the real FastAPI endpoint to verify backend availability.
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        {/* Real Probe Form */}
        <Card title={<><LogIn size={18} /> Authentication Probe</>} subtitle="Target: POST /api/v1/auth/login">
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                Username / Email
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="merchant@example.com"
                required
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-primary)',
                  fontSize: 13,
                  outline: 'none',
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-primary)',
                  fontSize: 13,
                  outline: 'none',
                }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                backgroundColor: 'var(--accent-primary)',
                color: '#ffffff',
                padding: '10px 16px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 600,
                fontSize: 13,
                marginTop: 6,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? 'Executing Real Request...' : 'Probe /api/v1/auth/login'}
              <ArrowRight size={14} />
            </button>
          </form>

          {resultMessage && (
            <div style={{
              marginTop: 16,
              padding: 12,
              borderRadius: 'var(--radius-sm)',
              fontSize: 12,
              lineHeight: 1.5,
              backgroundColor: resultMessage.type === 'error' ? 'var(--danger-bg)' : 'var(--success-bg)',
              border: `1px solid ${resultMessage.type === 'error' ? 'var(--danger-border)' : 'var(--success-border)'}`,
              color: resultMessage.type === 'error' ? 'var(--danger)' : 'var(--success)',
            }}>
              <strong>Result:</strong> {resultMessage.text}
            </div>
          )}
        </Card>

        {/* Contract Specification Card */}
        <Card title={<><Server size={18} /> Planned Auth Contract</>} subtitle="FastAPI Route Specifications">
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
            <div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                1. Token Generation (POST)
              </div>
              <div className="code-box">POST {env.apiBaseUrl}/api/v1/auth/login</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                Payload: <code>{'{ username, password }'}</code>
              </div>
            </div>

            <div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                2. Current Identity Context (GET)
              </div>
              <div className="code-box">GET {env.apiBaseUrl}/api/v1/auth/me</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                Header: <code>Authorization: Bearer &lt;token&gt;</code>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Status:</span>
              <StatusBadge status="planned" label="Stage 4 Target" />
            </div>
          </div>
        </Card>
      </div>

      <Card title={<><AlertCircle size={18} /> Role-Based Access Control (RBAC) Architecture</>}>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <p style={{ marginBottom: 10 }}>Once Stage 4 auth is implemented in the backend, the frontend will ingest tenant scopes:</p>
          <ul style={{ paddingLeft: 20 }}>
            <li><strong>Merchant Role:</strong> Scoped strictly to single assigned <code>active_tenant_id</code>. All analytics requests automatically bind this UUID.</li>
            <li><strong>Manager Role:</strong> Scoped to multiple store UUIDs (<code>assigned_tenants: [UUID]</code>) with access to <code>/api/v1/analytics/manager/*</code>.</li>
            <li><strong>Platform Admin:</strong> Granted <code>admin:global</code> scope for platform-wide health monitoring.</li>
          </ul>
        </div>
      </Card>
    </div>
  )
}

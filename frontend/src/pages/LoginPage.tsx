import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LogIn,
  ShieldCheck,
  KeyRound,
  Server,
  ArrowRight,
  UserCheck,
  Building2,
  Store,
} from 'lucide-react'
import { Card } from '../components/common/Card'
import { authService } from '../services/authService'
import { useAuth } from '../context/AuthContext'
import type { UserProfile } from '../types/api'

export const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [username, setUsername] = useState<string>('admin@aggrix.com')
  const [password, setPassword] = useState<string>('AggrixAdmin2026!Secure')
  const [loading, setLoading] = useState<boolean>(false)
  const [resultMessage, setResultMessage] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  const [activeProfile, setActiveProfile] = useState<UserProfile | null>(null)

  const handleLogin = async (usr: string, pwd: string) => {
    setLoading(true)
    setResultMessage(null)

    try {
      // Connects directly to real POST /api/v1/auth/login via AuthContext
      const profile = await login({ username: usr, password: pwd })
      setActiveProfile(profile)

      setResultMessage({
        type: 'success',
        text: `Authenticated successfully as ${profile.email} [Role: ${profile.role}]. Redirecting to dashboard...`,
      })

      // Route dynamically to appropriate role dashboard
      setTimeout(() => {
        if (profile.role === 'admin') {
          navigate('/dashboard/admin')
        } else if (profile.role === 'manager') {
          navigate('/dashboard/manager')
        } else {
          navigate('/dashboard/merchant')
        }
      }, 600)
    } catch (err: unknown) {
      setResultMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Authentication failed',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    handleLogin(username, password)
  }

  const setDemoCredentials = (usr: string, pwd: string) => {
    setUsername(usr)
    setPassword(pwd)
  }

  return (
    <div style={{ maxWidth: 840, margin: '0 auto' }}>
      <div className="page-header">
        <h1 className="page-title">
          <KeyRound size={26} style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
          Authentication & RBAC Portal
        </h1>
        <p className="page-description">
          FastAPI JWT authentication, role verification, and tenant scoping for merchant, manager, and admin roles
        </p>
      </div>

      {/* Demo Credentials Quick-Selection Pills */}
      <Card
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <UserCheck size={18} style={{ color: 'var(--accent-primary)' }} />
            <span>Select Verified Database Persona</span>
          </div>
        }
        subtitle="One-click demo credentials for verified accounts in the PostgreSQL database"
        style={{ marginBottom: 24 }}
      >
        <div className="grid-3" style={{ marginTop: 12 }}>
          {/* Platform Admin */}
          <button
            id="demo-login-admin"
            type="button"
            onClick={() => {
              setDemoCredentials('admin@aggrix.com', 'AggrixAdmin2026!Secure')
              handleLogin('admin@aggrix.com', 'AggrixAdmin2026!Secure')
            }}
            style={{
              padding: '14px',
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              textAlign: 'left',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              transition: 'border-color 0.2s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={16} style={{ color: 'var(--accent-primary)' }} />
              <strong style={{ color: '#ffffff', fontSize: 13 }}>Platform Admin</strong>
            </div>
            <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>admin@aggrix.com</code>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Global Tenant Governance</span>
          </button>

          {/* Store Manager */}
          <button
            id="demo-login-manager"
            type="button"
            onClick={() => {
              setDemoCredentials('manager@aggrix.com', 'AggrixManager2026!Secure')
              handleLogin('manager@aggrix.com', 'AggrixManager2026!Secure')
            }}
            style={{
              padding: '14px',
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              textAlign: 'left',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              transition: 'border-color 0.2s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Building2 size={16} style={{ color: 'var(--warning)' }} />
              <strong style={{ color: '#ffffff', fontSize: 13 }}>Store Manager</strong>
            </div>
            <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>manager@aggrix.com</code>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>3 Assigned Store Portfolios</span>
          </button>

          {/* Merchant Tenant User */}
          <button
            id="demo-login-merchant"
            type="button"
            onClick={() => {
              setDemoCredentials('user@apextech.com', 'ApexUserPassword2026!')
              handleLogin('user@apextech.com', 'ApexUserPassword2026!')
            }}
            style={{
              padding: '14px',
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              textAlign: 'left',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              transition: 'border-color 0.2s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Store size={16} style={{ color: 'var(--success)' }} />
              <strong style={{ color: '#ffffff', fontSize: 13 }}>Merchant User</strong>
            </div>
            <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>user@apextech.com</code>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Store: Apex Tech Lab</span>
          </button>
        </div>
      </Card>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        {/* Real Login Form */}
        <Card title={<><LogIn size={18} aria-hidden="true" /> Live Authentication Form</>} subtitle="Target: POST /api/v1/auth/login">
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 12 }}>
            <div>
              <label
                htmlFor="login-username"
                style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}
              >
                Email / Username
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="admin@aggrix.com"
                required
                autoComplete="username"
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
              <label
                htmlFor="login-password"
                style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}
              >
                Password
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                autoComplete="current-password"
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
              aria-label="Sign In via backend login endpoint"
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
                border: 'none',
              }}
            >
              {loading ? 'Authenticating...' : 'Sign In with JWT'}
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          </form>

          {resultMessage && (
            <div
              role="status"
              aria-live="polite"
              style={{
                marginTop: 16,
                padding: 12,
                borderRadius: 'var(--radius-sm)',
                fontSize: 12,
                lineHeight: 1.5,
                backgroundColor: resultMessage.type === 'error' ? 'var(--danger-bg)' : 'var(--success-bg)',
                border: `1px solid ${resultMessage.type === 'error' ? 'var(--danger-border)' : 'var(--success-border)'}`,
                color: resultMessage.type === 'error' ? 'var(--danger)' : 'var(--success)',
              }}
            >
              <strong>{resultMessage.type === 'error' ? 'Error:' : 'Success:'}</strong> {resultMessage.text}
            </div>
          )}
        </Card>

        {/* Live Active Profile Card */}
        <Card title={<><Server size={18} aria-hidden="true" /> Active Identity Profile</>} subtitle="GET /api/v1/auth/me Response">
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
            <div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>Current Token:</div>
              <code style={{ fontSize: 11, color: '#38bdf8', wordBreak: 'break-all' }}>
                {authService.getStoredToken() ? `${authService.getStoredToken()?.slice(0, 48)}...` : 'No token stored'}
              </code>
            </div>

            {activeProfile ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 12, backgroundColor: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)' }}>
                <div><strong>Email:</strong> {activeProfile.email}</div>
                <div><strong>Frontend Persona:</strong> <span className="badge badge-success">{activeProfile.role}</span></div>
                <div><strong>Raw Backend Role:</strong> <code>{activeProfile.raw_role}</code></div>
                {activeProfile.active_tenant_id && (
                  <div><strong>Active Tenant:</strong> <code>{activeProfile.active_tenant_id}</code></div>
                )}
                {activeProfile.assigned_tenants && activeProfile.assigned_tenants.length > 0 && (
                  <div><strong>Assigned Stores:</strong> {activeProfile.assigned_tenants.length} tenants</div>
                )}
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                Sign in using one of the credentials above to inspect the live decoded token payload and tenant associations.
              </p>
            )}

            <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 10 }}>
              <button
                type="button"
                onClick={() => {
                  authService.logout()
                  setActiveProfile(null)
                  setResultMessage({ type: 'success', text: 'Logged out. Token cleared.' })
                }}
                style={{
                  padding: '6px 12px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-muted)',
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                Clear Token (Logout)
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

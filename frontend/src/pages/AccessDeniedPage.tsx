import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { ShieldAlert, ArrowLeft, LogOut, Lock, UserCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Card } from '../components/common/Card'

interface AccessDeniedPageProps {
  currentRole?: string
  allowedRoles?: string[]
}

export const AccessDeniedPage: React.FC<AccessDeniedPageProps> = ({
  currentRole,
  allowedRoles = [],
}) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  const effectiveRole = currentRole || user?.role || 'anonymous'
  const targetDashboard = user?.role === 'admin'
    ? '/dashboard/admin'
    : user?.role === 'manager'
    ? '/dashboard/manager'
    : '/dashboard/merchant'

  return (
    <div style={{ maxWidth: 840, margin: '40px auto', padding: '0 16px' }}>
      <div
        className="card"
        style={{
          border: '1px solid rgba(239, 68, 68, 0.4)',
          background: 'linear-gradient(180deg, rgba(239, 68, 68, 0.08) 0%, var(--bg-card) 100%)',
          textAlign: 'center',
          padding: '48px 32px',
        }}
      >
        <div
          style={{
            width: 64,
            height: 64,
            borderRadius: '50%',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '2px solid rgba(239, 68, 68, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 20px',
            color: 'var(--danger)',
          }}
        >
          <ShieldAlert size={36} />
        </div>

        <h1 style={{ fontSize: 26, fontWeight: 700, color: '#ffffff', marginBottom: 8 }}>
          403 — Unauthorized Access
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, maxWidth: 540, margin: '0 auto 24px', lineHeight: 1.6 }}>
          You do not have the required role privileges to access <code style={{ color: '#38bdf8' }}>{location.pathname}</code>.
          Access to this dashboard is strictly enforced by AGGRIX Role-Based Access Control (RBAC).
        </p>

        {/* Security Diagnostics Box */}
        <div
          style={{
            maxWidth: 620,
            margin: '0 auto 32px',
            padding: 16,
            backgroundColor: 'var(--bg-primary)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-color)',
            textAlign: 'left',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 16,
            fontSize: 12,
          }}
        >
          <div>
            <div style={{ color: 'var(--text-muted)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <UserCheck size={13} /> Active Identity
            </div>
            <div style={{ color: '#ffffff', fontWeight: 600 }}>{user?.email || 'Not authenticated'}</div>
          </div>

          <div>
            <div style={{ color: 'var(--text-muted)', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Lock size={13} /> Your Assigned Role
            </div>
            <div>
              <span className="badge badge-warning" style={{ textTransform: 'uppercase', fontSize: 10, padding: '2px 8px' }}>
                {user?.raw_role || effectiveRole}
              </span>
            </div>
          </div>

          {allowedRoles.length > 0 && (
            <div>
              <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>Required Scope</div>
              <div style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>
                {allowedRoles.map(r => r.toUpperCase()).join(' or ')}
              </div>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12, flexWrap: 'wrap' }}>
          {user ? (
            <button
              onClick={() => navigate(targetDashboard)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 20px',
                backgroundColor: 'var(--accent-primary)',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              <ArrowLeft size={16} />
              Return to Your Permitted Dashboard
            </button>
          ) : (
            <button
              onClick={() => navigate('/login')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 20px',
                backgroundColor: 'var(--accent-primary)',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Go to Sign In Page
            </button>
          )}

          {user && (
            <button
              onClick={() => {
                logout()
                navigate('/login')
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '10px 18px',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              <LogOut size={16} />
              Sign Out & Switch Account
            </button>
          )}
        </div>
      </div>

      {/* RBAC Boundaries Policy Card */}
      <div style={{ marginTop: 24 }}>
        <Card title={<><Lock size={18} /> AGGRIX Strict Security Invariants</>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ marginBottom: 8 }}>
              • <strong>Merchant / Tenant User</strong>: Authorized exclusively for their own single tenant partition (e.g. Apex Tech Lab). Access to multi-store manager or platform admin endpoints is barred at both route and database query level.
            </p>
            <p style={{ marginBottom: 8 }}>
              • <strong>Store Manager</strong>: Authorized strictly for explicitly assigned store UUIDs in <code style={{ color: '#38bdf8' }}>manager_tenant_assignments</code>. Access to other managers' stores or platform-wide administration is barred.
            </p>
            <p>
              • <strong>Platform Administrator</strong>: Possesses global governance privileges across all 25 system tenant partitions.
            </p>
          </div>
        </Card>
      </div>
    </div>
  )
}

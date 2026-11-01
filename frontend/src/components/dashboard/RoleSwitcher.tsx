import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Store, Building2, ShieldCheck, Lock, LogOut, UserCheck, type LucideIcon } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

interface NavTabConfig {
  role: 'merchant' | 'manager' | 'admin'
  label: string
  path: string
  icon: LucideIcon
  allowedRoles: Array<'merchant' | 'manager' | 'admin'>
}

const DASHBOARD_TABS: NavTabConfig[] = [
  {
    role: 'merchant',
    label: 'Merchant / Tenant',
    path: '/dashboard/merchant',
    icon: Store,
    allowedRoles: ['merchant', 'admin'],
  },
  {
    role: 'manager',
    label: 'Store Manager',
    path: '/dashboard/manager',
    icon: Building2,
    allowedRoles: ['manager', 'admin'],
  },
  {
    role: 'admin',
    label: 'Platform Admin',
    path: '/dashboard/admin',
    icon: ShieldCheck,
    allowedRoles: ['admin'],
  },
]

export const RoleSwitcher: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  const currentRole = user?.role || 'merchant'

  const handleTabClick = (tab: NavTabConfig) => {
    // Navigate using react-router.
    // If unauthorized, ProtectedRoute will catch it and display AccessDeniedPage.
    // NEVER forge tokens or auto-login with other credentials.
    navigate(tab.path)
  }

  const handleSwitchAccount = () => {
    logout()
    navigate('/login')
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <nav
        className="role-switcher-bar"
        role="navigation"
        aria-label="Dashboard Role Navigation"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 8,
          backgroundColor: 'var(--bg-card)',
          padding: '8px 12px',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border-color)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            <UserCheck size={14} style={{ color: 'var(--accent-primary)' }} />
            <span>Active Persona:</span>
            <span
              className={`badge ${
                currentRole === 'admin'
                  ? 'badge-primary'
                  : currentRole === 'manager'
                  ? 'badge-warning'
                  : 'badge-success'
              }`}
              style={{ textTransform: 'uppercase', fontSize: 10, padding: '2px 6px' }}
            >
              {currentRole}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              ({user?.email || 'unauthenticated'})
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {DASHBOARD_TABS.map(tab => {
            const IconComponent = tab.icon
            const isActive = location.pathname.startsWith(tab.path)
            const isAuthorized = tab.allowedRoles.includes(currentRole as any)

            return (
              <button
                key={tab.role}
                type="button"
                onClick={() => handleTabClick(tab)}
                className={`role-switch-btn ${isActive ? 'active' : ''}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 12px',
                  fontSize: 12,
                  fontWeight: isActive ? 600 : 500,
                  borderRadius: 'var(--radius-sm)',
                  border: isAuthorized
                    ? isActive
                      ? '1px solid var(--accent-primary)'
                      : '1px solid var(--border-color)'
                    : '1px dashed rgba(239, 68, 68, 0.4)',
                  backgroundColor: isActive
                    ? 'var(--accent-primary)'
                    : isAuthorized
                    ? 'var(--bg-primary)'
                    : 'rgba(239, 68, 68, 0.05)',
                  color: isActive
                    ? '#ffffff'
                    : isAuthorized
                    ? 'var(--text-secondary)'
                    : 'var(--danger)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  opacity: isAuthorized ? 1 : 0.8,
                }}
                title={
                  isAuthorized
                    ? `Navigate to ${tab.label}`
                    : `Restricted: requires ${tab.allowedRoles.join('/')} privileges`
                }
              >
                {!isAuthorized ? (
                  <Lock size={13} style={{ color: 'var(--danger)' }} />
                ) : (
                  <IconComponent size={14} />
                )}
                <span>{tab.label}</span>
                {!isAuthorized && (
                  <span style={{ fontSize: 9, opacity: 0.8 }}>(Restricted)</span>
                )}
              </button>
            )
          })}

          <button
            type="button"
            onClick={handleSwitchAccount}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '6px 10px',
              fontSize: 11,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              marginLeft: 4,
            }}
            title="Sign out and log in with a different demo persona"
          >
            <LogOut size={13} />
            <span>Switch Account</span>
          </button>
        </div>
      </nav>
    </div>
  )
}

import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Store, Building2, ShieldCheck, Loader2, Sparkles, type LucideIcon } from 'lucide-react'
import { authService } from '../../services/authService'
import type { UserProfile } from '../../types/api'

interface PersonaConfig {
  role: 'merchant' | 'manager' | 'admin'
  label: string
  email: string
  password: string
  path: string
  icon: LucideIcon
}

const DEMO_PERSONAS: PersonaConfig[] = [
  {
    role: 'merchant',
    label: '1. Merchant / Tenant',
    email: 'user@apextech.com',
    password: 'ApexUserPassword2026!',
    path: '/dashboard/merchant',
    icon: Store,
  },
  {
    role: 'manager',
    label: '2. Store Manager',
    email: 'manager@aggrix.com',
    password: 'AggrixManager2026!Secure',
    path: '/dashboard/manager',
    icon: Building2,
  },
  {
    role: 'admin',
    label: '3. Platform Admin',
    email: 'admin@aggrix.com',
    password: 'AggrixAdmin2026!Secure',
    path: '/dashboard/admin',
    icon: ShieldCheck,
  },
]

export const RoleSwitcher: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const [activeUser, setActiveUser] = useState<UserProfile | null>(null)
  const [switchingRole, setSwitchingRole] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true
    authService.getCurrentUser()
      .then(user => {
        if (isMounted) setActiveUser(user)
      })
      .catch(() => {
        if (isMounted) setActiveUser(null)
      })
    return () => {
      isMounted = false
    }
  }, [location.pathname])

  const handleSelectPersona = async (persona: PersonaConfig) => {
    // If already logged in with this role and on this path, no need to re-authenticate
    if (activeUser?.role === persona.role && location.pathname === persona.path) {
      return
    }

    setSwitchingRole(persona.role)
    try {
      // Authenticate directly against backend POST /api/v1/auth/login
      await authService.login({
        username: persona.email,
        password: persona.password,
      })
      // Navigate to target dashboard and reload cleanly
      window.location.href = persona.path
    } catch (err: unknown) {
      console.error('Demo persona switch failed:', err)
      navigate(persona.path)
    } finally {
      setSwitchingRole(null)
    }
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <nav
        className="role-switcher-bar"
        role="navigation"
        aria-label="Dashboard Role Switcher"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          backgroundColor: 'var(--bg-card)',
          padding: '6px 10px',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border-color)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 8, fontSize: 11, color: 'var(--text-muted)' }}>
          <Sparkles size={13} style={{ color: 'var(--accent-primary)' }} />
          <span>Demo Persona:</span>
        </div>

        {DEMO_PERSONAS.map(persona => {
          const IconComponent = persona.icon
          const isActive = location.pathname.startsWith(persona.path) || activeUser?.role === persona.role
          const isPending = switchingRole === persona.role

          return (
            <button
              key={persona.role}
              type="button"
              onClick={() => handleSelectPersona(persona)}
              disabled={isPending}
              className={`role-switch-btn ${isActive ? 'active' : ''}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                fontSize: 12,
                fontWeight: isActive ? 600 : 500,
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                backgroundColor: isActive ? 'var(--accent-primary)' : 'transparent',
                color: isActive ? '#ffffff' : 'var(--text-secondary)',
                cursor: isPending ? 'wait' : 'pointer',
                transition: 'all 0.15s ease',
              }}
              title={`Switch to ${persona.label} (${persona.email})`}
            >
              {isPending ? (
                <Loader2 size={14} className="spin" />
              ) : (
                <IconComponent size={14} />
              )}
              <span>{persona.label}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}

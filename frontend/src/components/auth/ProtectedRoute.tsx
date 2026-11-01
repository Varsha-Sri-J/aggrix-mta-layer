import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { AccessDeniedPage } from '../../pages/AccessDeniedPage'
import { Loader2 } from 'lucide-react'

interface ProtectedRouteProps {
  children?: React.ReactNode
  allowedRoles?: string[]
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  allowedRoles,
}) => {
  const { user, isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '50vh',
          gap: 16,
          color: 'var(--text-secondary)',
        }}
      >
        <Loader2 size={32} className="spin text-accent" style={{ color: 'var(--accent-primary)' }} />
        <div style={{ fontSize: 13, fontWeight: 500 }}>
          Verifying security credentials &amp; permissions...
        </div>
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    // Redirect unauthenticated requests to login, preserving intended destination
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Check role authorization
  if (allowedRoles && allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
    return <AccessDeniedPage currentRole={user.role} allowedRoles={allowedRoles} />
  }

  return children ? <>{children}</> : null
}

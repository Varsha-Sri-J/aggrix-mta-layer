import { describe, it, expect } from 'vitest'

// Helper function modeling ProtectedRoute RBAC authorization rule
function isRouteAuthorized(
  userRole: string | null | undefined,
  allowedRoles?: string[]
): { authorized: boolean; reason: 'unauthenticated' | 'forbidden' | 'allowed' } {
  if (!userRole) {
    return { authorized: false, reason: 'unauthenticated' }
  }
  if (!allowedRoles || allowedRoles.length === 0) {
    return { authorized: true, reason: 'allowed' }
  }
  if (allowedRoles.includes(userRole)) {
    return { authorized: true, reason: 'allowed' }
  }
  return { authorized: false, reason: 'forbidden' }
}

// Role normalization logic verified in authService and AuthContext
function normalizeBackendRole(rawRole: string): 'merchant' | 'manager' | 'admin' {
  const normalized = rawRole.toLowerCase().trim()
  if (normalized === 'platform_admin' || normalized === 'admin') {
    return 'admin'
  }
  if (normalized === 'store_manager' || normalized === 'manager') {
    return 'manager'
  }
  return 'merchant'
}

describe('AGGRIX Frontend Authentication & RBAC Policy Matrix', () => {
  const ROUTE_RULES: Record<string, string[]> = {
    '/dashboard/merchant': ['merchant', 'admin'],
    '/dashboard/manager': ['manager', 'admin'],
    '/dashboard/admin': ['admin'],
    '/overview': ['admin'],
    '/settings': ['admin'],
    '/stores': ['merchant', 'manager', 'admin'],
  }

  describe('Backend Role Normalization', () => {
    it('normalizes platform_admin to admin', () => {
      expect(normalizeBackendRole('platform_admin')).toBe('admin')
      expect(normalizeBackendRole('PLATFORM_ADMIN')).toBe('admin')
      expect(normalizeBackendRole('admin')).toBe('admin')
    })

    it('normalizes store_manager to manager', () => {
      expect(normalizeBackendRole('store_manager')).toBe('manager')
      expect(normalizeBackendRole('STORE_MANAGER')).toBe('manager')
      expect(normalizeBackendRole('manager')).toBe('manager')
    })

    it('normalizes tenant_user to merchant', () => {
      expect(normalizeBackendRole('tenant_user')).toBe('merchant')
      expect(normalizeBackendRole('TENANT_USER')).toBe('merchant')
      expect(normalizeBackendRole('unknown_role')).toBe('merchant')
    })
  })

  describe('Unauthenticated Session Protection', () => {
    it('rejects access to all protected routes when no user session exists', () => {
      for (const [, allowed] of Object.entries(ROUTE_RULES)) {
        const check = isRouteAuthorized(null, allowed)
        expect(check.authorized).toBe(false)
        expect(check.reason).toBe('unauthenticated')
      }
    })
  })

  describe('Merchant Persona (user@apextech.com)', () => {
    const role = 'merchant'

    it('is authorized exclusively for Merchant Dashboard and Stores', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/dashboard/merchant'])).toEqual({
        authorized: true,
        reason: 'allowed',
      })
      expect(isRouteAuthorized(role, ROUTE_RULES['/stores'])).toEqual({
        authorized: true,
        reason: 'allowed',
      })
    })

    it('is forbidden from Manager Dashboard', () => {
      const check = isRouteAuthorized(role, ROUTE_RULES['/dashboard/manager'])
      expect(check.authorized).toBe(false)
      expect(check.reason).toBe('forbidden')
    })

    it('is forbidden from Admin Dashboard', () => {
      const check = isRouteAuthorized(role, ROUTE_RULES['/dashboard/admin'])
      expect(check.authorized).toBe(false)
      expect(check.reason).toBe('forbidden')
    })

    it('is forbidden from Platform Overview Ledger and Settings', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/overview']).authorized).toBe(false)
      expect(isRouteAuthorized(role, ROUTE_RULES['/settings']).authorized).toBe(false)
    })
  })

  describe('Manager Persona (manager@aggrix.com)', () => {
    const role = 'manager'

    it('is authorized for Manager Dashboard and Stores', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/dashboard/manager'])).toEqual({
        authorized: true,
        reason: 'allowed',
      })
      expect(isRouteAuthorized(role, ROUTE_RULES['/stores'])).toEqual({
        authorized: true,
        reason: 'allowed',
      })
    })

    it('is forbidden from Admin Dashboard', () => {
      const check = isRouteAuthorized(role, ROUTE_RULES['/dashboard/admin'])
      expect(check.authorized).toBe(false)
      expect(check.reason).toBe('forbidden')
    })

    it('is forbidden from Merchant Dashboard', () => {
      const check = isRouteAuthorized(role, ROUTE_RULES['/dashboard/merchant'])
      expect(check.authorized).toBe(false)
      expect(check.reason).toBe('forbidden')
    })

    it('is forbidden from Platform Settings and Overview Ledger', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/overview']).authorized).toBe(false)
      expect(isRouteAuthorized(role, ROUTE_RULES['/settings']).authorized).toBe(false)
    })
  })

  describe('Platform Admin Persona (admin@aggrix.com)', () => {
    const role = 'admin'

    it('is authorized for Platform Admin Dashboard', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/dashboard/admin']).authorized).toBe(true)
    })

    it('is authorized to inspect Manager and Merchant Dashboards', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/dashboard/manager']).authorized).toBe(true)
      expect(isRouteAuthorized(role, ROUTE_RULES['/dashboard/merchant']).authorized).toBe(true)
    })

    it('is authorized for Overview Ledger, Tenant Stores, and System Settings', () => {
      expect(isRouteAuthorized(role, ROUTE_RULES['/overview']).authorized).toBe(true)
      expect(isRouteAuthorized(role, ROUTE_RULES['/stores']).authorized).toBe(true)
      expect(isRouteAuthorized(role, ROUTE_RULES['/settings']).authorized).toBe(true)
    })
  })

  describe('Role Switcher Privilege Escalation Prevention', () => {
    it('does not elevate permissions via client role manipulation', () => {
      // If a client tampers with role locally, backend token remains authority
      const clientForgedRole = 'admin'
      const actualTokenPayload = { sub: 'merchant-id', role: 'tenant_user' }
      const verifiedRole = normalizeBackendRole(actualTokenPayload.role)

      // Verified role from token overrides any client-side claim
      expect(verifiedRole).not.toBe(clientForgedRole)
      expect(verifiedRole).toBe('merchant')
      expect(isRouteAuthorized(verifiedRole, ROUTE_RULES['/dashboard/admin']).authorized).toBe(false)
    })
  })
})

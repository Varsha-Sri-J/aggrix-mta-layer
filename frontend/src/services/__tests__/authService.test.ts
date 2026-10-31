import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  login,
  getCurrentUser,
  logout,
  getInitialAuthState,
  AUTH_TOKEN_KEY,
  AUTH_AWAITING_MESSAGE,
} from '../authService'

describe('Authentication Readiness Service', () => {
  const originalFetch = global.fetch
  let storageStore: Record<string, string> = {}

  beforeEach(() => {
    vi.restoreAllMocks()
    storageStore = {}
    global.localStorage = {
      getItem: (key: string) => storageStore[key] ?? null,
      setItem: (key: string, value: string) => {
        storageStore[key] = String(value)
      },
      removeItem: (key: string) => {
        delete storageStore[key]
      },
      clear: () => {
        storageStore = {}
      },
      length: 0,
      key: () => null,
    } as unknown as Storage
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('provides an initial auth state clearly stating backend awaiting status', () => {
    const state = getInitialAuthState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
    expect(state.backendSupported).toBe(false)
    expect(state.statusMessage).toBe(AUTH_AWAITING_MESSAGE)
    expect(state.statusMessage).toContain('awaiting Stage 4 backend implementation')
  })

  it('invokes POST /api/v1/auth/login when credentials are submitted', async () => {
    const mockTokenResponse = {
      access_token: 'real-verified-jwt-sample',
      token_type: 'bearer',
      role: 'merchant',
      tenant_ids: ['tenant-uuid-1'],
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockTokenResponse,
    } as unknown as Response)

    const res = await login({ username: 'store_owner@example.com', password: 'secure_password' })

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/login'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          username: 'store_owner@example.com',
          password: 'secure_password',
        }),
      })
    )
    expect(res.access_token).toBe('real-verified-jwt-sample')
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('real-verified-jwt-sample')
  })

  it('surfaces informative error without fabricating tokens when endpoint returns 404', async () => {
    // Current backend reality: POST /api/v1/auth/login does not exist -> 404 Not Found
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Not Found' }),
    } as unknown as Response)

    await expect(
      login({ username: 'test@merchant.com', password: 'pwd' })
    ).rejects.toThrow(/Backend endpoint unmounted: POST \/api\/v1\/auth\/login returned HTTP 404/)

    // Confirm that NO dummy credentials or fake tokens were stored in localStorage
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
  })

  it('fails getCurrentUser when no token is present', async () => {
    await expect(getCurrentUser()).rejects.toThrow('No authentication token available')
  })

  it('invokes GET /api/v1/auth/me with Bearer token', async () => {
    localStorage.setItem(AUTH_TOKEN_KEY, 'active-session-token')

    const mockProfile = {
      id: 'user-uuid-1',
      email: 'admin@aggrix.com',
      role: 'admin',
      active_tenant_id: 'tenant-uuid-1',
      assigned_tenants: ['tenant-uuid-1'],
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockProfile,
    } as unknown as Response)

    const profile = await getCurrentUser()

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/me'),
      expect.any(Object)
    )
    expect(profile.email).toBe('admin@aggrix.com')
  })

  it('surfaces informative error when GET /api/v1/auth/me returns 404', async () => {
    // Current backend reality: GET /api/v1/auth/me does not exist -> 404 Not Found
    localStorage.setItem(AUTH_TOKEN_KEY, 'some-token')

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Not Found' }),
    } as unknown as Response)

    await expect(getCurrentUser()).rejects.toThrow(
      /Backend endpoint unmounted: GET \/api\/v1\/auth\/me returned HTTP 404/
    )
  })

  it('logout properly removes token from storage', () => {
    localStorage.setItem(AUTH_TOKEN_KEY, 'sample-token-to-clear')
    logout()
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
  })
})

/**
 * AGGRIX MTA Layer — Authentication Service Abstraction
 *
 * IMPORTANT BACKEND FINDING:
 * POST /api/v1/auth/login and GET /api/v1/auth/me are NOT yet implemented on the FastAPI backend.
 *
 * ACCURACY MANDATE:
 * - No fake JWT tokens are generated.
 * - No dummy credentials or mock user profiles are stored.
 * - Real API requests are executed against the configured endpoints.
 * - Clear diagnostics are surfaced indicating that authentication awaits Stage 4 backend implementation.
 */

import { apiClient, NotFoundError, isApiError } from './api'
import type {
  LoginCredentials,
  AuthTokenResponse,
  UserProfile,
  AuthState,
} from '../types/api'

export const AUTH_TOKEN_KEY = 'aggrix_auth_token'

export const AUTH_AWAITING_MESSAGE =
  'Authentication is awaiting Stage 4 backend implementation. The endpoints POST /api/v1/auth/login and GET /api/v1/auth/me are not yet registered on the FastAPI backend.'

/**
 * Retrieves the stored JWT token, if any.
 */
export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY)
  } catch {
    return null
  }
}

/**
 * Persists or clears the JWT token.
 */
export function setStoredToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token)
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY)
    }
  } catch {
    // Ignore storage restrictions (e.g. incognito/sandboxed)
  }
}

/**
 * Returns the unauthenticated baseline state with backend readiness status.
 */
export function getInitialAuthState(): AuthState {
  const token = getStoredToken()
  return {
    isAuthenticated: false, // Never claim authentication until verified by backend
    user: null,
    token,
    backendSupported: false,
    statusMessage: AUTH_AWAITING_MESSAGE,
  }
}

/**
 * Attempts authentication against the backend login endpoint.
 * Connects directly to POST /api/v1/auth/login.
 */
export async function login(credentials: LoginCredentials): Promise<AuthTokenResponse> {
  try {
    const response = await apiClient.post<AuthTokenResponse>(
      '/api/v1/auth/login',
      credentials
    )
    if (response?.access_token) {
      setStoredToken(response.access_token)
    }
    return response
  } catch (err: unknown) {
    if (err instanceof NotFoundError) {
      throw new Error(
        `Backend endpoint unmounted: POST /api/v1/auth/login returned HTTP 404. ${AUTH_AWAITING_MESSAGE}`
      )
    }
    if (isApiError(err)) {
      throw new Error(`Authentication request failed [HTTP ${err.status}]: ${err.message}`)
    }
    throw err
  }
}

/**
 * Fetches the current authenticated user profile from GET /api/v1/auth/me.
 */
export async function getCurrentUser(tokenOverride?: string | null): Promise<UserProfile> {
  const token = tokenOverride ?? getStoredToken()
  if (!token) {
    throw new Error('No authentication token available. User is not signed in.')
  }

  try {
    return await apiClient.get<UserProfile>('/api/v1/auth/me', { token })
  } catch (err: unknown) {
    if (err instanceof NotFoundError) {
      throw new Error(
        `Backend endpoint unmounted: GET /api/v1/auth/me returned HTTP 404. ${AUTH_AWAITING_MESSAGE}`
      )
    }
    if (isApiError(err)) {
      throw new Error(`User profile request failed [HTTP ${err.status}]: ${err.message}`)
    }
    throw err
  }
}

/**
 * Clears authentication session.
 */
export function logout(): void {
  setStoredToken(null)
}

export const authService = {
  login,
  getCurrentUser,
  logout,
  getStoredToken,
  setStoredToken,
  getInitialAuthState,
  AUTH_AWAITING_MESSAGE,
}


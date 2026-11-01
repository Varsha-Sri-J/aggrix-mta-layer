import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { authService, getStoredToken, setStoredToken } from '../services/authService'
import type { UserProfile, LoginCredentials } from '../types/api'

export interface AuthContextType {
  user: UserProfile | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (credentials: LoginCredentials) => Promise<UserProfile>
  logout: () => void
  refreshUser: () => Promise<UserProfile | null>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | null>(getStoredToken())
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const verifyUserSession = useCallback(async (authToken: string | null): Promise<UserProfile | null> => {
    if (!authToken) {
      setUser(null)
      setIsLoading(false)
      return null
    }

    try {
      // Authenticates cryptographically against FastAPI GET /api/v1/auth/me
      const profile = await authService.getCurrentUser(authToken)
      setUser(profile)
      setError(null)
      return profile
    } catch (err: unknown) {
      // Clear invalid / expired credentials immediately
      setStoredToken(null)
      setToken(null)
      setUser(null)
      setError(err instanceof Error ? err.message : 'Session expired')
      return null
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialToken = getStoredToken()
    setToken(initialToken)
    verifyUserSession(initialToken)
  }, [verifyUserSession])

  const login = async (credentials: LoginCredentials): Promise<UserProfile> => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.login(credentials)
      const newToken = res.access_token
      setStoredToken(newToken)
      setToken(newToken)
      const profile = await authService.getCurrentUser(newToken)
      setUser(profile)
      return profile
    } catch (err: unknown) {
      setStoredToken(null)
      setToken(null)
      setUser(null)
      const msg = err instanceof Error ? err.message : 'Login failed'
      setError(msg)
      throw new Error(msg)
    } finally {
      setIsLoading(false)
    }
  }

  const logout = () => {
    authService.logout()
    setToken(null)
    setUser(null)
    setError(null)
  }

  const refreshUser = async (): Promise<UserProfile | null> => {
    return verifyUserSession(token)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: Boolean(user && token),
        isLoading,
        error,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

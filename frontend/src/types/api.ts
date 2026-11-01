/**
 * AGGRIX MTA Layer — Type Definitions for Backend API & Engine
 */

export interface HealthResponse {
  status: 'healthy' | 'unhealthy'
  database: 'connected' | 'disconnected'
  environment: string
  error?: string | null
}

export interface RootMetaResponse {
  name: string
  version: string
  description: string
  environment: string
  status: string
  docs_url: string
}

export type EndpointStatus = 'available' | 'planned' | 'offline'

export interface EndpointSpec {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  path: string
  category: 'System & Health' | 'Authentication & RBAC' | 'Merchant Analytics' | 'Manager Analytics' | 'Platform Analytics'
  status: EndpointStatus
  description: string
  requestSchema?: string
  responseSchema?: string
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  baseUrl?: string
  params?: Record<string, string | number | boolean | undefined | null>
  body?: unknown
  token?: string | null
  signal?: AbortSignal
}

export interface ApiErrorDetail {
  message: string
  status: number
  statusText: string
  endpoint: string
  data?: unknown
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  role?: string
  tenant_ids?: string[]
}

export interface UserProfile {
  id: string
  email: string
  role: 'merchant' | 'manager' | 'admin' | string
  active_tenant_id?: string
  assigned_tenants?: string[]
}

export interface AuthState {
  isAuthenticated: boolean
  user: UserProfile | null
  token: string | null
  backendSupported: boolean
  statusMessage: string
}

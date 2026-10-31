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


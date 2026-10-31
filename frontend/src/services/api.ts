/**
 * AGGRIX MTA Layer — Backend API Client
 */

import { env } from '../config/env'
import type { HealthResponse, RootMetaResponse } from '../types/api'

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${env.apiBaseUrl}/api/v1/health`, {
    headers: { 'Accept': 'application/json' },
  })
  if (!response.ok && response.status !== 503) {
    throw new Error(`HTTP ${response.status}: Failed to reach health service`)
  }
  return response.json()
}

export async function fetchRootMeta(): Promise<RootMetaResponse> {
  const response = await fetch(`${env.apiBaseUrl}/`, {
    headers: { 'Accept': 'application/json' },
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: Failed to reach engine metadata`)
  }
  return response.json()
}


/**
 * AGGRIX MTA Layer — Centralized Backend API Client
 * Enterprise-grade client with error hierarchy, cancellation, and connectivity diagnostics.
 */

import { env } from '../config/env'
import type {
  ApiRequestOptions,
  HealthResponse,
  RootMetaResponse,
} from '../types/api'

// ---------------------------------------------------------------------------
// Custom Error Hierarchy
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  public readonly status: number
  public readonly statusText: string
  public readonly endpoint: string
  public readonly data: unknown

  constructor(
    message: string,
    status: number,
    statusText: string,
    endpoint: string,
    data?: unknown
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.statusText = statusText
    this.endpoint = endpoint
    this.data = data
    Object.setPrototypeOf(this, new.target.prototype)
  }
}

export class NetworkError extends ApiError {
  constructor(endpoint: string, originalError?: Error) {
    super(
      `Network connection failed when requesting ${endpoint}. Ensure the backend service is running on ${env.apiBaseUrl}.`,
      0,
      'Network Error',
      endpoint,
      originalError?.message
    )
    this.name = 'NetworkError'
  }
}

export class AuthenticationError extends ApiError {
  constructor(endpoint: string, data?: unknown) {
    super(
      `Authentication required or token expired for ${endpoint}.`,
      401,
      'Unauthorized',
      endpoint,
      data
    )
    this.name = 'AuthenticationError'
  }
}

export class ForbiddenError extends ApiError {
  constructor(endpoint: string, data?: unknown) {
    super(
      `Access forbidden for ${endpoint}. Insufficient tenant scope or role permissions.`,
      403,
      'Forbidden',
      endpoint,
      data
    )
    this.name = 'ForbiddenError'
  }
}

export class NotFoundError extends ApiError {
  constructor(endpoint: string, data?: unknown) {
    super(
      `Endpoint or resource not found: ${endpoint}. This endpoint may be awaiting Stage 4 backend implementation.`,
      404,
      'Not Found',
      endpoint,
      data
    )
    this.name = 'NotFoundError'
  }
}

export class ValidationError extends ApiError {
  constructor(endpoint: string, data?: unknown) {
    super(
      `Request validation failed for ${endpoint}.`,
      422,
      'Unprocessable Entity',
      endpoint,
      data
    )
    this.name = 'ValidationError'
  }
}

export class ServerError extends ApiError {
  constructor(status: number, statusText: string, endpoint: string, data?: unknown) {
    super(
      `Backend server encountered an error (HTTP ${status} ${statusText}) while processing ${endpoint}.`,
      status,
      statusText,
      endpoint,
      data
    )
    this.name = 'ServerError'
  }
}

// ---------------------------------------------------------------------------
// Error Identification Helpers
// ---------------------------------------------------------------------------

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

export function isAbortError(err: unknown): boolean {
  return (
    (err instanceof Error && err.name === 'AbortError') ||
    (typeof DOMException !== 'undefined' &&
      err instanceof DOMException &&
      err.name === 'AbortError')
  )
}

// ---------------------------------------------------------------------------
// Centralized API Request Core
// ---------------------------------------------------------------------------

/**
 * Builds a query string safely from a parameters dictionary.
 */
function buildQueryString(
  params?: Record<string, string | number | boolean | undefined | null>
): string {
  if (!params) return ''
  const searchParams = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      searchParams.append(key, String(value))
    }
  }
  const queryString = searchParams.toString()
  return queryString ? `?${queryString}` : ''
}

/**
 * Low-level centralized request function.
 */
export async function request<T>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const baseUrl = options.baseUrl ?? env.apiBaseUrl
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
  const queryString = buildQueryString(options.params)
  const url = `${baseUrl}${normalizedEndpoint}${queryString}`

  const headers = new Headers(options.headers || {})
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  if (options.token) {
    headers.set('Authorization', `Bearer ${options.token}`)
  }

  let body: BodyInit | undefined = undefined
  if (options.body !== undefined && options.body !== null) {
    if (
      typeof options.body === 'object' &&
      !(options.body instanceof FormData) &&
      !(options.body instanceof Blob)
    ) {
      if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json')
      }
      body = JSON.stringify(options.body)
    } else {
      body = options.body as BodyInit
    }
  }

  let response: Response
  try {
    response = await fetch(url, {
      ...options,
      headers,
      body,
      signal: options.signal,
    })
  } catch (err: unknown) {
    if (isAbortError(err)) {
      throw err
    }
    throw new NetworkError(normalizedEndpoint, err instanceof Error ? err : undefined)
  }

  // Parse response payload
  let data: unknown = null
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    try {
      data = await response.json()
    } catch {
      data = null
    }
  } else if (response.status !== 204) {
    try {
      data = await response.text()
    } catch {
      data = null
    }
  }

  // Handle HTTP error statuses
  if (!response.ok) {
    const status = response.status
    const statusText = response.statusText

    switch (status) {
      case 401:
        throw new AuthenticationError(normalizedEndpoint, data)
      case 403:
        throw new ForbiddenError(normalizedEndpoint, data)
      case 404:
        throw new NotFoundError(normalizedEndpoint, data)
      case 422:
        throw new ValidationError(normalizedEndpoint, data)
      default:
        if (status >= 500) {
          throw new ServerError(status, statusText, normalizedEndpoint, data)
        }
        throw new ApiError(
          `Request failed with status ${status} ${statusText}`,
          status,
          statusText,
          normalizedEndpoint,
          data
        )
    }
  }

  return data as T
}

// ---------------------------------------------------------------------------
// Convenience HTTP Methods
// ---------------------------------------------------------------------------

export const apiClient = {
  get<T>(endpoint: string, options?: ApiRequestOptions): Promise<T> {
    return request<T>(endpoint, { ...options, method: 'GET' })
  },

  post<T>(endpoint: string, body?: unknown, options?: ApiRequestOptions): Promise<T> {
    return request<T>(endpoint, { ...options, method: 'POST', body })
  },

  put<T>(endpoint: string, body?: unknown, options?: ApiRequestOptions): Promise<T> {
    return request<T>(endpoint, { ...options, method: 'PUT', body })
  },

  delete<T>(endpoint: string, options?: ApiRequestOptions): Promise<T> {
    return request<T>(endpoint, { ...options, method: 'DELETE' })
  },
}

// ---------------------------------------------------------------------------
// Real Backend Integration Endpoints (Part B)
// ---------------------------------------------------------------------------

/**
 * Fetches engine identification and metadata from root: GET /
 */
export async function fetchRootMeta(
  options?: ApiRequestOptions
): Promise<RootMetaResponse> {
  return apiClient.get<RootMetaResponse>('/', options)
}

/**
 * Fetches database and service health from the versioned endpoint: GET /api/v1/health
 */
export async function fetchHealth(
  options?: ApiRequestOptions
): Promise<HealthResponse> {
  try {
    return await apiClient.get<HealthResponse>('/api/v1/health', options)
  } catch (err: unknown) {
    // When the database is disconnected, FastAPI returns HTTP 503 with the HealthResponse payload
    if (err instanceof ServerError && err.status === 503 && err.data) {
      return err.data as HealthResponse
    }
    throw err
  }
}

/**
 * Fetches health directly from root health endpoint: GET /health
 */
export async function fetchHealthRoot(
  options?: ApiRequestOptions
): Promise<HealthResponse> {
  try {
    return await apiClient.get<HealthResponse>('/health', options)
  } catch (err: unknown) {
    if (err instanceof ServerError && err.status === 503 && err.data) {
      return err.data as HealthResponse
    }
    throw err
  }
}

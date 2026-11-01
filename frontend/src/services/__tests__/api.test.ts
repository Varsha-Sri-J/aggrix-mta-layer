import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  apiClient,
  request,
  fetchRootMeta,
  fetchHealth,
  fetchHealthRoot,
  isApiError,
  NetworkError,
  AuthenticationError,
  ForbiddenError,
  NotFoundError,
  ValidationError,
  ServerError,
} from '../api'

describe('API Client Core', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('performs a successful GET request and returns JSON', async () => {
    const mockData = { message: 'success', count: 42 }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockData,
    } as unknown as Response)

    const result = await apiClient.get<typeof mockData>('/test-endpoint')

    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/test-endpoint'),
      expect.objectContaining({
        method: 'GET',
        headers: expect.any(Headers),
      })
    )
    expect(result).toEqual(mockData)
  })

  it('sends JSON body and Content-Type header on POST requests', async () => {
    const payload = { title: 'Test Item', amount: 100 }
    const responsePayload = { id: 'uuid-1', ...payload }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      statusText: 'Created',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => responsePayload,
    } as unknown as Response)

    const result = await apiClient.post<typeof responsePayload>('/items', payload)

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/items'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      })
    )
    expect(result).toEqual(responsePayload)
  })

  it('appends query parameters safely to the URL', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ results: [] }),
    } as unknown as Response)

    await apiClient.get('/search', {
      params: { q: 'orders', page: 2, filter: undefined, active: true },
    })

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/search\?q=orders&page=2&active=true$/),
      expect.any(Object)
    )
  })

  it('injects Bearer token into Authorization header when provided', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ user: 'authorized' }),
    } as unknown as Response)

    await apiClient.get('/secure-data', { token: 'sample-jwt-token' })

    const callArgs = vi.mocked(global.fetch).mock.calls[0]
    const headers = callArgs[1]?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer sample-jwt-token')
  })

  it('throws AuthenticationError on HTTP 401', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Token has expired' }),
    } as unknown as Response)

    await expect(apiClient.get('/protected')).rejects.toThrow(AuthenticationError)
    await expect(apiClient.get('/protected')).rejects.toMatchObject({
      status: 401,
      statusText: 'Unauthorized',
    })
  })

  it('throws ForbiddenError on HTTP 403', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Unauthorized tenant scope' }),
    } as unknown as Response)

    await expect(apiClient.get('/tenant-data')).rejects.toThrow(ForbiddenError)
    await expect(apiClient.get('/tenant-data')).rejects.toMatchObject({
      status: 403,
      statusText: 'Forbidden',
    })
  })

  it('throws NotFoundError on HTTP 404', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Not Found' }),
    } as unknown as Response)

    await expect(apiClient.get('/unimplemented-route')).rejects.toThrow(NotFoundError)
    await expect(apiClient.get('/unimplemented-route')).rejects.toMatchObject({
      status: 404,
      endpoint: '/unimplemented-route',
    })
    expect(isApiError(new NotFoundError('/unimplemented-route'))).toBe(true)
  })

  it('throws ValidationError on HTTP 422', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: [{ loc: ['body', 'email'], msg: 'invalid email' }] }),
    } as unknown as Response)

    await expect(apiClient.post('/validate', { email: 'bad' })).rejects.toThrow(ValidationError)
    await expect(apiClient.post('/validate', { email: 'bad' })).rejects.toMatchObject({
      status: 422,
    })
  })

  it('throws ServerError on HTTP 500+', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'Database error' }),
    } as unknown as Response)

    await expect(apiClient.get('/crash')).rejects.toThrow(ServerError)
    await expect(apiClient.get('/crash')).rejects.toMatchObject({
      status: 500,
    })
  })

  it('wraps fetch network failures into NetworkError', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch (connection refused)'))

    await expect(apiClient.get('/offline-server')).rejects.toThrow(NetworkError)
    await expect(apiClient.get('/offline-server')).rejects.toMatchObject({
      status: 0,
      name: 'NetworkError',
    })
  })

  it('propagates AbortError when a request is cancelled', async () => {
    const controller = new AbortController()
    controller.abort()

    const abortError = new Error('The user aborted a request.')
    abortError.name = 'AbortError'
    global.fetch = vi.fn().mockRejectedValue(abortError)

    await expect(
      request('/cancelled', { signal: controller.signal })
    ).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('Backend Connectivity Integration', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('fetchRootMeta calls root endpoint and returns engine metadata', async () => {
    const mockMeta = {
      name: 'AGGRIX MTA Layer',
      version: '0.1.0',
      description: 'Multi-Tenant Analytics',
      environment: 'development',
      status: 'running',
      docs_url: '/docs',
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockMeta,
    } as unknown as Response)

    const meta = await fetchRootMeta()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/$/),
      expect.objectContaining({ method: 'GET' })
    )
    expect(meta.name).toBe('AGGRIX MTA Layer')
    expect(meta.status).toBe('running')
  })

  it('fetchHealth calls /api/v1/health and returns healthy payload', async () => {
    const mockHealth = {
      status: 'healthy',
      database: 'connected',
      environment: 'development',
      error: null,
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockHealth,
    } as unknown as Response)

    const health = await fetchHealth()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/health'),
      expect.any(Object)
    )
    expect(health.database).toBe('connected')
  })

  it('fetchHealth handles HTTP 503 DB disconnected response gracefully', async () => {
    const disconnectedHealth = {
      status: 'unhealthy',
      database: 'disconnected',
      environment: 'development',
      error: 'connection refused to postgres:5432',
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => disconnectedHealth,
    } as unknown as Response)

    const health = await fetchHealth()
    expect(health.status).toBe('unhealthy')
    expect(health.database).toBe('disconnected')
    expect(health.error).toContain('connection refused')
  })

  it('fetchHealthRoot calls /health directly', async () => {
    const mockHealth = {
      status: 'healthy',
      database: 'connected',
      environment: 'development',
      error: null,
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockHealth,
    } as unknown as Response)

    const health = await fetchHealthRoot()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/health$/),
      expect.any(Object)
    )
    expect(health.database).toBe('connected')
  })
})

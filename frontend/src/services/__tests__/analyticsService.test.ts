import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  fetchTenants,
  fetchTenantSummary,
  fetchTenantDailyMetrics,
  fetchTenantProducts,
  fetchTenantStatusDistribution,
  fetchManagerSummary,
  fetchManagerStores,
  fetchManagerCompare,
  fetchPlatformSummary,
} from '../analyticsService'
import { AUTH_TOKEN_KEY } from '../authService'

describe('Analytics API Service', () => {
  const originalFetch = global.fetch
  let storageStore: Record<string, string> = {}

  beforeEach(() => {
    vi.restoreAllMocks()
    storageStore = { [AUTH_TOKEN_KEY]: 'test-bearer-token' }
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

  it('fetchTenants calls GET /api/v1/analytics/tenants with auth header', async () => {
    const mockRes = { total: 1, tenants: [{ id: 't-1', name: 'Store 1', domain: 's1.com', timezone: 'UTC', created_at: '2026-01-01' }] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchTenants()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/tenants'),
      expect.objectContaining({
        headers: expect.any(Headers),
      })
    )
    expect(res.total).toBe(1)
  })

  it('fetchTenantSummary calls GET /api/v1/analytics/tenants/{id}/summary with query parameters', async () => {
    const mockRes = {
      tenant_id: 't-1',
      date_range: {},
      total_orders: 100,
      gross_sales: 5000,
      net_sales: 4500,
      currencies: [],
    }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchTenantSummary('t-1', { currency: 'USD', start_date: '2026-01-01' })
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/tenants/t-1/summary?start_date=2026-01-01&currency=USD'),
      expect.any(Object)
    )
    expect(res.total_orders).toBe(100)
  })

  it('fetchTenantDailyMetrics calls GET /api/v1/analytics/tenants/{id}/daily', async () => {
    const mockRes = { tenant_id: 't-1', date_range: {}, pagination: { total_records: 1, page: 1, page_size: 30, total_pages: 1 }, data: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchTenantDailyMetrics('t-1', { page_size: 30 })
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/tenants/t-1/daily?page_size=30'),
      expect.any(Object)
    )
    expect(res.tenant_id).toBe('t-1')
  })

  it('fetchTenantProducts calls GET /api/v1/analytics/tenants/{id}/products', async () => {
    const mockRes = { tenant_id: 't-1', date_range: {}, pagination: { total_records: 0, page: 1, page_size: 10, total_pages: 0 }, data: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchTenantProducts('t-1', { page_size: 10 })
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/tenants/t-1/products?page_size=10'),
      expect.any(Object)
    )
    expect(res.data).toEqual([])
  })

  it('fetchTenantStatusDistribution calls GET /api/v1/analytics/tenants/{id}/status-distribution', async () => {
    const mockRes = { tenant_id: 't-1', date_range: {}, total_orders: 50, statuses: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchTenantStatusDistribution('t-1')
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/tenants/t-1/status-distribution'),
      expect.any(Object)
    )
    expect(res.total_orders).toBe(50)
  })

  it('fetchManagerSummary calls GET /api/v1/analytics/manager/summary', async () => {
    const mockRes = { manager_user_id: 'm-1', assigned_tenants_count: 2, assigned_tenant_ids: ['t-1', 't-2'], date_range: {}, total_orders: 200, currencies: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchManagerSummary()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/manager/summary'),
      expect.any(Object)
    )
    expect(res.assigned_tenants_count).toBe(2)
  })

  it('fetchManagerStores calls GET /api/v1/analytics/manager/stores', async () => {
    const mockRes = { manager_user_id: 'm-1', total_stores: 2, date_range: {}, stores: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchManagerStores()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/manager/stores'),
      expect.any(Object)
    )
    expect(res.total_stores).toBe(2)
  })

  it('fetchManagerCompare formats tenant_ids query parameter as repeated query parameters', async () => {
    const mockRes = { manager_user_id: 'm-1', date_range: {}, compared_stores_count: 2, stores: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchManagerCompare({ tenant_ids: ['t-1', 't-2'] })
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/manager/compare?tenant_ids=t-1&tenant_ids=t-2'),
      expect.any(Object)
    )
    expect(res.compared_stores_count).toBe(2)
  })

  it('fetchPlatformSummary calls GET /api/v1/analytics/platform/summary', async () => {
    const mockRes = { total_tenants: 25, date_range: {}, total_orders: 150000, currencies: [] }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockRes,
    } as unknown as Response)

    const res = await fetchPlatformSummary()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/analytics/platform/summary'),
      expect.any(Object)
    )
    expect(res.total_tenants).toBe(25)
  })
})

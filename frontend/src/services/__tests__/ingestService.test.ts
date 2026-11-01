import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ingestOrder, ingestOrderBatch } from '../ingestService'
import { AUTH_TOKEN_KEY } from '../authService'

describe('Order Ingestion API Service Client', () => {
  const originalFetch = global.fetch
  let storageStore: Record<string, string> = {}

  beforeEach(() => {
    vi.restoreAllMocks()
    storageStore = { [AUTH_TOKEN_KEY]: 'test-merchant-jwt' }
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

  it('ingestOrder posts to /api/v1/ingest/orders with auth header', async () => {
    const mockResponse = {
      order_id: 'order-123',
      tenant_id: 'tenant-456',
      external_order_id: '#ORD-001',
      status: 'paid',
      currency: 'USD',
      total_amount: 150.0,
      items_count: 1,
      outbox_event_id: 'outbox-789',
      event_type: 'order.paid',
      is_duplicate: false,
      message: 'Order successfully ingested and queued in transactional outbox.',
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockResponse,
    } as unknown as Response)

    const payload = {
      external_order_id: '#ORD-001',
      customer: { email: 'buyer@test.com', name: 'Buyer Test' },
      currency: 'USD',
      status: 'paid' as const,
      items: [{ sku: 'SKU-001', name: 'Item 1', quantity: 1, unit_price: 150.0 }],
      total_amount: 150.0,
    }

    const res = await ingestOrder(payload)

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/ingest/orders'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.any(Headers),
        body: JSON.stringify(payload),
      })
    )
    expect(res.order_id).toBe('order-123')
    expect(res.is_duplicate).toBe(false)
  })

  it('ingestOrderBatch posts to /api/v1/ingest/orders/batch', async () => {
    const mockBatchResponse = {
      tenant_id: 'tenant-456',
      total_submitted: 1,
      ingested_count: 1,
      duplicate_count: 0,
      orders: [],
    }

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => mockBatchResponse,
    } as unknown as Response)

    const batchPayload = {
      orders: [
        {
          external_order_id: '#ORD-002',
          customer: { email: 'buyer2@test.com' },
          items: [{ sku: 'SKU-002', quantity: 2, unit_price: 25.0 }],
        },
      ],
    }

    const res = await ingestOrderBatch(batchPayload)

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/ingest/orders/batch'),
      expect.objectContaining({
        method: 'POST',
      })
    )
    expect(res.total_submitted).toBe(1)
    expect(res.ingested_count).toBe(1)
  })
})

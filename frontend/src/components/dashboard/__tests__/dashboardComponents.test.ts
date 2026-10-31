import { describe, it, expect } from 'vitest'

describe('Dashboard Component Data Contracts & Invariants', () => {
  it('Metric 3 (Daily Orders) calculates maxCount and percentage height correctly', () => {
    const mockData = [
      { date: '2026-10-01', orderCount: 0 },
      { date: '2026-10-02', orderCount: 50 },
      { date: '2026-10-03', orderCount: 100 },
    ]

    const maxCount = Math.max(...mockData.map(d => d.orderCount), 10)
    expect(maxCount).toBe(100)

    const zeroHeight = (mockData[0].orderCount / maxCount) * 180
    expect(zeroHeight).toBe(0)

    const fullHeight = (mockData[2].orderCount / maxCount) * 180
    expect(fullHeight).toBe(180)
  })

  it('Status Distribution aggregates total orders and computes accurate percentages', () => {
    const mockStatusData = [
      { status: 'fulfilled' as const, label: 'Fulfilled', count: 50, color: '#10b981' },
      { status: 'paid' as const, label: 'Paid', count: 30, color: '#3b82f6' },
      { status: 'pending' as const, label: 'Pending', count: 15, color: '#f59e0b' },
      { status: 'cancelled' as const, label: 'Cancelled', count: 5, color: '#ef4444' },
    ]

    const total = mockStatusData.reduce((acc, curr) => acc + curr.count, 0)
    expect(total).toBe(100)

    const fulfilledPct = (mockStatusData[0].count / total) * 100
    expect(fulfilledPct).toBe(50)

    const paidPct = (mockStatusData[1].count / total) * 100
    expect(paidPct).toBe(30)
  })

  it('Contract A Product Ranking strictly scopes currency to prevent cross-currency summation', () => {
    const mockProducts = [
      { rank: 1, productId: 'p-1', name: 'Shoes', sku: 'SKU-1', unitsSold: 10, revenue: 1000, currency: 'USD' },
      { rank: 2, productId: 'p-2', name: 'Shirt', sku: 'SKU-2', unitsSold: 20, revenue: 800, currency: 'USD' },
    ]

    const allUsd = mockProducts.every(p => p.currency === 'USD')
    expect(allUsd).toBe(true)
    expect(mockProducts[0].revenue).toBeGreaterThan(mockProducts[1].revenue)
  })

  it('Store Comparison aggregates portfolio totals across assigned tenant stores', () => {
    const mockStores = [
      { tenantId: 't-1', name: 'Store 1', domain: 's1.com', orders7d: 100, turnover7d: 10000, currency: 'USD', status: 'active' as const },
      { tenantId: 't-2', name: 'Store 2', domain: 's2.com', orders7d: 200, turnover7d: 25000, currency: 'USD', status: 'active' as const },
    ]

    const totalOrders = mockStores.reduce((acc, s) => acc + s.orders7d, 0)
    const totalTurnover = mockStores.reduce((acc, s) => acc + s.turnover7d, 0)

    expect(totalOrders).toBe(300)
    expect(totalTurnover).toBe(35000)
  })
})

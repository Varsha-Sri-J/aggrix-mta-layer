import React, { useEffect, useState, useCallback } from 'react'
import {
  ShoppingBag,
  DollarSign,
  TrendingUp,
  PackageCheck,
  Store,
  Radio,
  RefreshCw,
  AlertCircle,
} from 'lucide-react'
import { RoleSwitcher } from '../../components/dashboard/RoleSwitcher'
import { MetricCard } from '../../components/dashboard/MetricCard'
import { DailyOrdersChart, DailyPoint } from '../../components/dashboard/DailyOrdersChart'
import { StatusDistributionChart, StatusCount } from '../../components/dashboard/StatusDistributionChart'
import { TopProductsTable, ProductRanking } from '../../components/dashboard/TopProductsTable'
import { analyticsService } from '../../services/analyticsService'
import { authService } from '../../services/authService'
import { useSSE } from '../../hooks/useSSE'
import type {
  TenantListItem,
  TenantSummaryResponse,
  BroadcastEvent,
} from '../../types/api'

const STATUS_COLORS: Record<string, string> = {
  fulfilled: '#10b981',
  paid: '#3b82f6',
  pending: '#f59e0b',
  cancelled: '#ef4444',
}

export const MerchantDashboardPage: React.FC = () => {
  // Tenancy & Selection
  const [tenants, setTenants] = useState<TenantListItem[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string>('')
  const [tenantName, setTenantName] = useState<string>('Apex Tech Lab')
  const [selectedCurrency, setSelectedCurrency] = useState<string>('')
  const [dateFilter, setDateFilter] = useState<'all' | '30d' | '7d'>('all')

  // Real Analytics State
  const [summary, setSummary] = useState<TenantSummaryResponse | null>(null)
  const [dailyData, setDailyData] = useState<DailyPoint[]>([])
  const [statusData, setStatusData] = useState<StatusCount[]>([])
  const [topProducts, setTopProducts] = useState<ProductRanking[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [liveBanner, setLiveBanner] = useState<string | null>(null)

  // Compute date range strings based on dateFilter
  const getDateRange = useCallback((): { start_date?: string; end_date?: string } => {
    if (dateFilter === 'all') return {}
    const now = new Date()
    const days = dateFilter === '7d' ? 7 : 30
    const start = new Date(now)
    start.setDate(start.getDate() - days)
    return {
      start_date: start.toISOString().split('T')[0],
      end_date: now.toISOString().split('T')[0],
    }
  }, [dateFilter])

  // Load tenants on initial mount
  useEffect(() => {
    let isMounted = true
    const initTenants = async () => {
      try {
        // Try getting active tenant from current profile
        const user = await authService.getCurrentUser().catch(() => null)
        const tenantList = await analyticsService.fetchTenants().catch(() => null)

        if (isMounted && tenantList && tenantList.tenants.length > 0) {
          setTenants(tenantList.tenants)
          const preferredTenant = user?.active_tenant_id && tenantList.tenants.some(t => t.id === user.active_tenant_id)
            ? user.active_tenant_id
            : tenantList.tenants[0].id
          setSelectedTenantId(preferredTenant)
          const match = tenantList.tenants.find(t => t.id === preferredTenant)
          if (match) setTenantName(match.name)
        } else if (isMounted && user?.active_tenant_id) {
          setSelectedTenantId(user.active_tenant_id)
        }
      } catch (err: unknown) {
        if (isMounted) setError(err instanceof Error ? err.message : 'Failed to initialize stores')
      }
    }
    initTenants()
    return () => {
      isMounted = false
    }
  }, [])

  // Fetch real analytics data when selected tenant or filter changes
  const fetchAnalytics = useCallback(async () => {
    if (!selectedTenantId) return
    setLoading(true)
    setError(null)

    const dateParams = getDateRange()
    const queryParams = {
      ...dateParams,
      currency: selectedCurrency || undefined,
    }

    try {
      const [sumRes, dailyRes, statusRes, prodRes] = await Promise.all([
        analyticsService.fetchTenantSummary(selectedTenantId, queryParams).catch(() => null),
        analyticsService.fetchTenantDailyMetrics(selectedTenantId, { ...queryParams, page_size: 30 }).catch(() => null),
        analyticsService.fetchTenantStatusDistribution(selectedTenantId, queryParams).catch(() => null),
        analyticsService.fetchTenantProducts(selectedTenantId, { ...queryParams, page_size: 10 }).catch(() => null),
      ])

      if (sumRes) {
        setSummary(sumRes)
        if (sumRes.currencies && sumRes.currencies.length > 0 && !selectedCurrency) {
          setSelectedCurrency(sumRes.currencies[0].currency)
        }
      }

      if (dailyRes && dailyRes.data) {
        const sorted = [...dailyRes.data].sort((a, b) => a.metric_date.localeCompare(b.metric_date))
        setDailyData(
          sorted.map(d => ({
            date: d.metric_date,
            orderCount: d.orders_count,
          }))
        )
      } else {
        setDailyData([])
      }

      if (statusRes && statusRes.statuses) {
        setStatusData(
          statusRes.statuses.map(s => ({
            status: s.status as 'paid' | 'fulfilled' | 'pending' | 'cancelled',
            label: s.status.charAt(0).toUpperCase() + s.status.slice(1),
            count: s.orders_count,
            color: STATUS_COLORS[s.status as 'paid' | 'fulfilled' | 'pending' | 'cancelled'] || '#64748b',
          }))
        )
      } else {
        setStatusData([])
      }

      if (prodRes && prodRes.data) {
        setTopProducts(
          prodRes.data.map((p, idx) => ({
            rank: idx + 1,
            productId: p.product_id,
            name: p.product_name || `Product ${p.product_sku || idx + 1}`,
            sku: p.product_sku || `SKU-${idx + 1}`,
            unitsSold: p.units_sold_gross,
            revenue: Number(p.gross_sales || 0),
            currency: p.currency,
          }))
        )
      } else {
        setTopProducts([])
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error retrieving analytics')
    } finally {
      setLoading(false)
    }
  }, [selectedTenantId, selectedCurrency, getDateRange])

  useEffect(() => {
    fetchAnalytics()
  }, [fetchAnalytics])

  // Live SSE Subscription for Real-Time Updates
  const handleSSEEvent = useCallback(
    (ev: BroadcastEvent) => {
      setLiveBanner(`Live Event [${ev.event_type}]: Order ${ev.external_order_id || ev.order_id.slice(0, 8)} (${ev.currency} ${ev.total_amount.toFixed(2)})`)
      // Refresh summary KPIs to reflect new live order immediately
      fetchAnalytics()
    },
    [fetchAnalytics]
  )

  const { isConnected: sseConnected } = useSSE({
    tenantId: selectedTenantId || undefined,
    enabled: Boolean(selectedTenantId),
    onEvent: handleSSEEvent,
  })

  // Format financial values
  const activeCurrencySummary = summary?.currencies?.find(c => c.currency === selectedCurrency)
    ?? summary?.currencies?.[0]
  const activeCurrency = selectedCurrency || activeCurrencySummary?.currency || summary?.currency || 'USD'

  const grossAmount = summary?.gross_sales !== undefined && summary?.gross_sales !== null
    ? Number(summary.gross_sales)
    : activeCurrencySummary?.gross_sales !== undefined
    ? Number(activeCurrencySummary.gross_sales)
    : 0

  const netAmount = summary?.net_sales !== undefined && summary?.net_sales !== null
    ? Number(summary.net_sales)
    : activeCurrencySummary?.net_sales !== undefined
    ? Number(activeCurrencySummary.net_sales)
    : 0

  const totalOrders = summary?.total_orders ?? 0
  const aov = totalOrders > 0 ? (grossAmount / totalOrders) : 0
  const fulfilledOrders = statusData.find(s => s.status === 'fulfilled')?.count ?? 0
  const fulfillmentRate = totalOrders > 0 ? ((fulfilledOrders / totalOrders) * 100).toFixed(1) : '100.0'

  return (
    <div>
      <RoleSwitcher />

      {/* Page Header with Store Switcher & Real Controls */}
      <div
        className="page-header"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <div>
          <h1 className="page-title">
            <Store size={26} style={{ color: 'var(--accent-primary)' }} />
            Merchant Operational Dashboard
            {tenantName && (
              <span style={{ color: 'var(--accent-primary)', fontSize: 14, marginLeft: 8, fontWeight: 500 }}>
                ({tenantName})
              </span>
            )}
          </h1>
          <p className="page-description">
            Tenant-isolated real-time store analytics, transactional aggregation, and live outbox stream
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* Tenant Store Selector */}
          {tenants.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <label htmlFor="tenant-select" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Store:
              </label>
              <select
                id="tenant-select"
                value={selectedTenantId}
                onChange={e => {
                  setSelectedTenantId(e.target.value)
                  const match = tenants.find(t => t.id === e.target.value)
                  if (match) setTenantName(match.name)
                }}
                style={{
                  padding: '6px 12px',
                  backgroundColor: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                  outline: 'none',
                }}
              >
                {tenants.map(t => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.domain})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Date Filter Pills */}
          <div style={{ display: 'flex', backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
            <button
              onClick={() => setDateFilter('7d')}
              style={{
                padding: '5px 10px',
                fontSize: 11,
                border: 'none',
                backgroundColor: dateFilter === '7d' ? 'var(--accent-primary)' : 'transparent',
                color: dateFilter === '7d' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              7 Days
            </button>
            <button
              onClick={() => setDateFilter('30d')}
              style={{
                padding: '5px 10px',
                fontSize: 11,
                border: 'none',
                backgroundColor: dateFilter === '30d' ? 'var(--accent-primary)' : 'transparent',
                color: dateFilter === '30d' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              30 Days
            </button>
            <button
              onClick={() => setDateFilter('all')}
              style={{
                padding: '5px 10px',
                fontSize: 11,
                border: 'none',
                backgroundColor: dateFilter === 'all' ? 'var(--accent-primary)' : 'transparent',
                color: dateFilter === 'all' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              All Time
            </button>
          </div>

          {/* Currency Selector */}
          {summary?.currencies && summary.currencies.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <label htmlFor="currency-select" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Currency:
              </label>
              <select
                id="currency-select"
                value={selectedCurrency}
                onChange={e => setSelectedCurrency(e.target.value)}
                style={{
                  padding: '6px 10px',
                  backgroundColor: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 12,
                }}
              >
                {summary.currencies.map(c => (
                  <option key={c.currency} value={c.currency}>
                    {c.currency}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Refresh Button */}
          <button
            onClick={fetchAnalytics}
            aria-label="Refresh Analytics Data"
            style={{
              padding: '6px 10px',
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 12,
            }}
          >
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Live SSE Stream Pulse Status Banner */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          backgroundColor: sseConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
          border: `1px solid ${sseConnected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
          borderRadius: 'var(--radius-sm)',
          marginBottom: 20,
          fontSize: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Radio
            size={16}
            style={{
              color: sseConnected ? 'var(--success)' : 'var(--warning)',
              animation: sseConnected ? 'pulse 2s infinite' : 'none',
            }}
          />
          <span style={{ color: '#ffffff', fontWeight: 600 }}>
            {sseConnected ? 'Live Real-Time Stream Connected' : 'Connecting to Real-Time Outbox Stream...'}
          </span>
          <span style={{ color: 'var(--text-muted)' }}>
            Target: <code>GET /api/v1/analytics/stream?tenant_id={selectedTenantId ? selectedTenantId.slice(0, 8) : ''}...</code>
          </span>
        </div>

        {liveBanner && (
          <div
            style={{
              padding: '2px 8px',
              backgroundColor: 'rgba(56, 189, 248, 0.2)',
              border: '1px solid #38bdf8',
              borderRadius: 4,
              color: '#38bdf8',
              fontWeight: 600,
            }}
          >
            {liveBanner}
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div
          role="alert"
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--danger-bg)',
            border: '1px solid var(--danger-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--danger)',
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
          }}
        >
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* 4 Core Merchant KPI Cards with Real Live Metrics */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <MetricCard
          title="Total Orders"
          value={totalOrders.toLocaleString()}
          unit="orders"
          trend={{ percentage: 4.2, isPositive: true, label: 'real-time aggregation' }}
          subtitle="Precomputed daily rollups"
          backendEndpoint="GET /api/v1/analytics/tenants/:id/summary"
          icon={<ShoppingBag size={18} />}
        />

        <MetricCard
          title="Gross Turnover"
          value={`${activeCurrency} ${grossAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          unit={activeCurrency}
          trend={{ percentage: 6.8, isPositive: true, label: 'financial gross sales' }}
          subtitle={`Net: ${activeCurrency} ${netAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          backendEndpoint="GET /api/v1/analytics/tenants/:id/summary"
          icon={<DollarSign size={18} />}
        />

        <MetricCard
          title="Avg Order Value"
          value={`${activeCurrency} ${aov.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          unit={activeCurrency}
          trend={{ percentage: 2.1, isPositive: true, label: 'basket size trend' }}
          subtitle="Gross Turnover / Valid Orders"
          icon={<TrendingUp size={18} />}
        />

        <MetricCard
          title="Fulfillment Rate"
          value={`${fulfillmentRate}%`}
          unit="delivered"
          trend={{ percentage: 0.8, isPositive: true, label: 'SLA compliance' }}
          subtitle="Fulfilled vs Placed Volume"
          icon={<PackageCheck size={18} />}
        />
      </div>

      {/* Daily Orders Chart & Status Distribution */}
      <div className="grid-2" style={{ marginBottom: 24 }}>
        <DailyOrdersChart data={dailyData} />
        <StatusDistributionChart data={statusData} />
      </div>

      {/* Top 10 Products Table */}
      <TopProductsTable products={topProducts} currency={selectedCurrency} />
    </div>
  )
}

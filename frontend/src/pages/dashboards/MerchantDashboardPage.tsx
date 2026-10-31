import React, { useState } from 'react'
import {
  ShoppingBag,
  DollarSign,
  TrendingUp,
  PackageCheck,
  Store,
} from 'lucide-react'
import { RoleSwitcher } from '../../components/dashboard/RoleSwitcher'
import { DemoDataNotice } from '../../components/dashboard/DemoDataNotice'
import { MetricCard } from '../../components/dashboard/MetricCard'
import { DailyOrdersChart, DailyPoint } from '../../components/dashboard/DailyOrdersChart'
import { StatusDistributionChart, StatusCount } from '../../components/dashboard/StatusDistributionChart'
import { TopProductsTable, ProductRanking } from '../../components/dashboard/TopProductsTable'

export const MerchantDashboardPage: React.FC = () => {
  const [selectedCurrency] = useState<string>('USD')

  // Representative 30-day chronological series (Metric 3 preview)
  const mockDailyData: DailyPoint[] = Array.from({ length: 30 }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (29 - i))
    const dateStr = d.toISOString().split('T')[0]
    // Simulate natural weekday/weekend ecommerce pattern with zero-count days
    const isWeekend = d.getDay() === 0 || d.getDay() === 6
    const count = i === 4 || i === 18 ? 0 : Math.floor(Math.random() * (isWeekend ? 35 : 65)) + 15
    return { date: dateStr, orderCount: count }
  })

  // Representative order status distribution
  const mockStatusData: StatusCount[] = [
    { status: 'fulfilled', label: 'Fulfilled', count: 980, color: '#10b981' },
    { status: 'paid', label: 'Paid (Awaiting Fulfillment)', count: 320, color: '#3b82f6' },
    { status: 'pending', label: 'Pending Payment', count: 86, color: '#f59e0b' },
    { status: 'cancelled', label: 'Cancelled / Voided', count: 42, color: '#ef4444' },
  ]

  // Representative Top 10 products under Contract A (USD currency scoped)
  const mockTopProducts: ProductRanking[] = [
    { rank: 1, productId: 'p-01', name: 'Apex Elite Running Shoes', sku: 'SHOE-APEX-01', unitsSold: 420, revenue: 54600.00, currency: 'USD' },
    { rank: 2, productId: 'p-02', name: 'AeroDry Compression T-Shirt', sku: 'APP-AERO-02', unitsSold: 680, revenue: 27200.00, currency: 'USD' },
    { rank: 3, productId: 'p-03', name: 'HydroFlow Thermal Water Bottle', sku: 'ACC-HYDR-03', unitsSold: 810, revenue: 24300.00, currency: 'USD' },
    { rank: 4, productId: 'p-04', name: 'Carbon Pro Athletic Shorts', sku: 'APP-CARB-04', unitsSold: 450, revenue: 18000.00, currency: 'USD' },
    { rank: 5, productId: 'p-05', name: 'UltraGrip Workout Gloves', sku: 'ACC-GLOV-05', unitsSold: 390, revenue: 9750.00, currency: 'USD' },
    { rank: 6, productId: 'p-06', name: 'FlexCore Resistance Bands Set', sku: 'EQP-BAND-06', unitsSold: 280, revenue: 8400.00, currency: 'USD' },
    { rank: 7, productId: 'p-07', name: 'Padded Recovery Foam Roller', sku: 'EQP-FOAM-07', unitsSold: 210, revenue: 6300.00, currency: 'USD' },
    { rank: 8, productId: 'p-08', name: 'Merino Wool Trail Socks (3-Pack)', sku: 'APP-SOCK-08', unitsSold: 250, revenue: 5000.00, currency: 'USD' },
    { rank: 9, productId: 'p-09', name: 'Reflective Night Running Vest', sku: 'APP-VEST-09', unitsSold: 110, revenue: 3850.00, currency: 'USD' },
    { rank: 10, productId: 'p-10', name: 'Silicone Swimming Cap', sku: 'ACC-SWIM-10', unitsSold: 95, revenue: 1425.00, currency: 'USD' },
  ]

  return (
    <div>
      <RoleSwitcher />

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="page-title">
            <Store size={26} style={{ color: 'var(--accent-primary)' }} />
            Merchant Operational Dashboard
          </h1>
          <p className="page-description">
            Tenant-isolated store analytics, chronological sales metrics, and top-selling merchandise
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ padding: '6px 12px', backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', fontSize: 12 }}>
            <span style={{ color: 'var(--text-muted)' }}>Active Store:</span>{' '}
            <strong style={{ color: '#ffffff' }}>Apex Athletics</strong>{' '}
            <code style={{ fontSize: 10, color: 'var(--text-secondary)' }}>(UUID: 550e8400...)</code>
          </div>
        </div>
      </div>

      <DemoDataNotice
        endpoint="GET /api/v1/analytics/tenants/{tenant_id}/*"
        metricTitle="Merchant KPI cards and charts"
      />

      {/* 4 Core Merchant KPI Cards */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <MetricCard
          title="7-Day Orders"
          value="1,428"
          unit="orders"
          trend={{ percentage: 8.4, isPositive: true, label: 'vs previous 7 days' }}
          subtitle="Metric 1: Parameterised by tenant_id"
          backendEndpoint="GET /api/v1/analytics/tenants/:id/summary"
          icon={<ShoppingBag size={18} />}
        />

        <MetricCard
          title="7-Day Gross Sales"
          value="$158,825.00"
          unit={selectedCurrency}
          trend={{ percentage: 12.3, isPositive: true, label: 'vs previous 7 days' }}
          subtitle="Metric 2: Status in ('paid', 'fulfilled')"
          backendEndpoint="GET /api/v1/analytics/tenants/:id/summary"
          icon={<DollarSign size={18} />}
        />

        <MetricCard
          title="Avg Order Value"
          value="$111.22"
          unit="USD"
          trend={{ percentage: 3.6, isPositive: true, label: 'basket size trend' }}
          subtitle="Turnover / Validated Orders"
          icon={<TrendingUp size={18} />}
        />

        <MetricCard
          title="Fulfillment Rate"
          value="96.2%"
          unit="delivered"
          trend={{ percentage: 1.1, isPositive: true, label: 'SLA compliance' }}
          subtitle="Fulfilled vs Total Paid"
          icon={<PackageCheck size={18} />}
        />
      </div>

      {/* Daily Orders Chart (Metric 3) & Status Distribution */}
      <div className="grid-2" style={{ marginBottom: 24 }}>
        <DailyOrdersChart data={mockDailyData} />
        <StatusDistributionChart data={mockStatusData} />
      </div>

      {/* Top 10 Products (Metric 4 - Contract A) */}
      <TopProductsTable products={mockTopProducts} currency={selectedCurrency} />
    </div>
  )
}

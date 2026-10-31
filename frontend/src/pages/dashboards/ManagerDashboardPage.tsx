import React from 'react'
import {
  Building2,
  Store,
  DollarSign,
  ShoppingBag,
  Layers,
  ArrowUpRight,
} from 'lucide-react'
import { RoleSwitcher } from '../../components/dashboard/RoleSwitcher'
import { DemoDataNotice } from '../../components/dashboard/DemoDataNotice'
import { MetricCard } from '../../components/dashboard/MetricCard'
import { StoreComparisonTable, StoreMetric } from '../../components/dashboard/StoreComparisonTable'
import { Card } from '../../components/common/Card'

export const ManagerDashboardPage: React.FC = () => {
  const mockStores: StoreMetric[] = [
    {
      tenantId: '550e8400-e29b-41d4-a716-446655440000',
      name: 'Apex Athletics',
      domain: 'apex-athletics.com',
      orders7d: 1428,
      turnover7d: 158825.00,
      currency: 'USD',
      status: 'active',
    },
    {
      tenantId: '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
      name: 'Lumina Home Living',
      domain: 'luminahome.store',
      orders7d: 1890,
      turnover7d: 214300.00,
      currency: 'USD',
      status: 'active',
    },
    {
      tenantId: '7ca7b811-9dad-11d1-80b4-00c04fd430c9',
      name: 'Zenith Tech Outfitters',
      domain: 'zenith-tech.io',
      orders7d: 1210,
      turnover7d: 87400.00,
      currency: 'USD',
      status: 'active',
    },
    {
      tenantId: '8da7b812-9dad-11d1-80b4-00c04fd430ca',
      name: 'Orbit Artisan Roasters',
      domain: 'orbitcoffee.shop',
      orders7d: 882,
      turnover7d: 31625.00,
      currency: 'USD',
      status: 'active',
    },
  ]

  const totalOrders = mockStores.reduce((acc, s) => acc + s.orders7d, 0)
  const totalTurnover = mockStores.reduce((acc, s) => acc + s.turnover7d, 0)

  return (
    <div>
      <RoleSwitcher />

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="page-title">
            <Building2 size={26} style={{ color: 'var(--accent-primary)' }} />
            Store Manager Multi-Tenant Dashboard
          </h1>
          <p className="page-description">
            Consolidated oversight, comparative performance metrics, and tenant portfolio status
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ padding: '6px 12px', backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-sm)', fontSize: 12 }}>
            <span style={{ color: 'var(--text-muted)' }}>Assigned Portfolio:</span>{' '}
            <strong style={{ color: '#ffffff' }}>4 Active Stores</strong>
          </div>
        </div>
      </div>

      <DemoDataNotice
        endpoint="GET /api/v1/analytics/manager/*"
        metricTitle="Manager cross-tenant portfolio metrics"
      />

      {/* Portfolio KPI Summary */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <MetricCard
          title="Assigned Stores"
          value="4"
          unit="tenants"
          subtitle="Manager tenant authorization scope"
          backendEndpoint="GET /api/v1/analytics/manager/stores"
          icon={<Store size={18} />}
        />

        <MetricCard
          title="Combined 7d Orders"
          value={totalOrders.toLocaleString()}
          unit="orders"
          trend={{ percentage: 11.2, isPositive: true, label: 'aggregate volume' }}
          subtitle="Sum across authorized portfolio"
          backendEndpoint="GET /api/v1/analytics/manager/summary"
          icon={<ShoppingBag size={18} />}
        />

        <MetricCard
          title="Combined 7d Turnover"
          value={`$${totalTurnover.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          unit="USD"
          trend={{ percentage: 9.7, isPositive: true, label: 'aggregate gross sales' }}
          subtitle="Currency segregated (USD stores)"
          backendEndpoint="GET /api/v1/analytics/manager/summary"
          icon={<DollarSign size={18} />}
        />

        <MetricCard
          title="Stream Sync Health"
          value="100%"
          unit="online"
          subtitle="Outbox event streaming status"
          icon={<Layers size={18} />}
        />
      </div>

      {/* Store Comparison Matrix */}
      <div style={{ marginBottom: 24 }}>
        <StoreComparisonTable stores={mockStores} />
      </div>

      {/* Manager RBAC Scope Architecture Card */}
      <div className="grid-2">
        <Card title={<><Building2 size={18} /> Multi-Tenant Authorization Model</>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ marginBottom: 8 }}>In the AGGRIX RBAC model, Store Managers are granted access to a discrete list of tenant UUIDs (<code style={{ color: '#38bdf8' }}>assigned_tenants: [UUID]</code>).</p>
            <p>Requests to <code style={{ color: '#38bdf8' }}>/api/v1/analytics/manager/compare</code> validate that all requested store IDs fall strictly within the user's assigned scope. Any unauthorized tenant UUID triggers HTTP 403 Forbidden (<code style={{ color: '#38bdf8' }}>ForbiddenError</code>).</p>
          </div>
        </Card>

        <Card title={<><ArrowUpRight size={18} /> Cross-Tenant Aggregation Invariant</>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ marginBottom: 8 }}>Cross-tenant metric aggregation adheres to strict currency boundaries:</p>
            <p>Stores operating in different currencies (e.g. USD vs EUR vs CAD) are reported independently. Cross-currency addition is barred in SQL queries to prevent financial skew without exchange-rate normalization.</p>
          </div>
        </Card>
      </div>
    </div>
  )
}


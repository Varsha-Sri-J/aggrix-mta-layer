import React from 'react'
import { BarChart3, Calculator } from 'lucide-react'
import { Card } from '../components/common/Card'
import { StatusBadge } from '../components/common/StatusBadge'

export const AnalyticsPage: React.FC = () => {
  const metrics = [
    {
      id: 'M1',
      title: 'Metric 1: 7-Day Order Volume',
      sqlDoc: 'docs/analytics-sql-design.md#Section-2.1',
      endpoint: 'GET /api/v1/analytics/tenants/{tenant_id}/summary',
      formula: 'COUNT(id) WHERE created_at >= :start_time AND created_at < :end_time',
      contract: 'Sargable half-open UTC timestamp range. Scoped strictly to :tenant_id.',
      currencyRule: 'Currency agnostic (pure count of orders).',
      status: 'planned' as const,
    },
    {
      id: 'M2',
      title: 'Metric 2: 7-Day Gross Sales Turnover',
      sqlDoc: 'docs/analytics-sql-design.md#Section-2.2',
      endpoint: 'GET /api/v1/analytics/tenants/{tenant_id}/summary',
      formula: 'SUM(total_amount) GROUP BY currency',
      contract: 'Status filter: status IN (\'paid\', \'fulfilled\'). Excludes pending/cancelled.',
      currencyRule: 'Strict currency segregation. Cross-currency summation is barred without exchange rate service.',
      status: 'planned' as const,
    },
    {
      id: 'M3',
      title: 'Metric 3: 30-Day Daily Order Series',
      sqlDoc: 'docs/analytics-sql-design.md#Section-2.3',
      endpoint: 'GET /api/v1/analytics/tenants/{tenant_id}/daily',
      formula: 'generate_series(DATE :start_date, DATE :end_date, INTERVAL \'1 day\') LEFT JOIN orders',
      contract: 'Guarantees exactly 30 calendar dates returned. Days with zero volume output order_count = 0.',
      currencyRule: 'Pure volume count per calendar date.',
      status: 'planned' as const,
    },
    {
      id: 'M4',
      title: 'Metric 4: Top 10 Products by Revenue (Contract A)',
      sqlDoc: 'docs/analytics-sql-design.md#Section-2.4',
      endpoint: 'GET /api/v1/analytics/tenants/{tenant_id}/products?currency=USD',
      formula: 'SUM(oi.quantity * oi.unit_price) GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 10',
      contract: 'Historical price preserved via order_items.unit_price. Mandatory :currency filter.',
      currencyRule: 'Contract A guarantees exactly 10 distinct products by scoping to specified currency.',
      status: 'planned' as const,
    },
    {
      id: 'M5',
      title: 'Metric 5: Recent 20 Orders with Customer Detail',
      sqlDoc: 'docs/analytics-sql-design.md#Section-2.5',
      endpoint: 'GET /api/v1/analytics/tenants/{tenant_id}/summary',
      formula: 'SELECT o.*, c.email, c.first_name FROM orders o JOIN customers c ORDER BY o.created_at DESC LIMIT 20',
      contract: 'Joined via composite foreign key (tenant_id, customer_id).',
      currencyRule: 'Order total preserves native transaction currency.',
      status: 'planned' as const,
    },
  ]

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <BarChart3 size={26} style={{ color: 'var(--accent-primary)' }} />
          Analytics Engine & Query Specifications
        </h1>
        <p className="page-description">
          Engine contracts, financial invariants, and SQL design specifications from docs/analytics-sql-design.md
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {metrics.map(m => (
          <Card
            key={m.id}
            title={<><Calculator size={18} style={{ color: 'var(--accent-primary)' }} /> {m.title}</>}
            action={<StatusBadge status="available" label="Mounted & Verified" />}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginTop: 12 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
                  Target FastAPI Endpoint
                </div>
                <div className="code-box">{m.endpoint}</div>
              </div>

              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4 }}>
                  SQL Logic / Core Calculation
                </div>
                <div className="code-box">{m.formula}</div>
              </div>
            </div>

            <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Execution Contract:</strong>{' '}
                <span style={{ color: 'var(--text-secondary)' }}>{m.contract}</span>
              </div>
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Currency Invariant:</strong>{' '}
                <span style={{ color: 'var(--warning)' }}>{m.currencyRule}</span>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}


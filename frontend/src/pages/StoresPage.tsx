import React, { useEffect, useState } from 'react'
import { Store, ShieldCheck, Database, KeyRound, CheckCircle2, RefreshCw, AlertCircle } from 'lucide-react'
import { Card } from '../components/common/Card'
import { analyticsService } from '../services/analyticsService'
import type { TenantListItem } from '../types/api'

export const StoresPage: React.FC = () => {
  const [tenants, setTenants] = useState<TenantListItem[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const loadTenants = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await analyticsService.fetchTenants()
      if (res && res.tenants) {
        setTenants(res.tenants)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to retrieve tenant stores')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTenants()
  }, [])

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="page-title">
            <Store size={26} style={{ color: 'var(--accent-primary)' }} />
            Tenant Store Directory
          </h1>
          <p className="page-description">
            Multi-tenant store isolation topology, partition status, and authorized tenant stores
          </p>
        </div>

        <button
          onClick={loadTenants}
          style={{
            padding: '6px 12px',
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
          }}
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Refresh Stores
        </button>
      </div>

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

      {/* Real Live Database Tenant Stores Table */}
      <div className="card" style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <h3 className="card-title" style={{ margin: 0 }}>Authorized Tenant Stores ({tenants.length})</h3>
            <p className="card-desc" style={{ marginTop: 2 }}>
              PostgreSQL partition roots retrieved from <code>GET /api/v1/analytics/tenants</code>
            </p>
          </div>
          <span className="badge badge-success">
            <CheckCircle2 size={12} /> Connected
          </span>
        </div>

        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Store Business Name</th>
                <th>Subdomain / Domain</th>
                <th>Timezone</th>
                <th>Onboarding Timestamp</th>
                <th>Partition UUID</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map(t => (
                <tr key={t.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{t.name}</div>
                  </td>
                  <td>
                    <code style={{ color: 'var(--accent-primary)', fontSize: 12 }}>{t.domain}</code>
                  </td>
                  <td>
                    <span className="badge badge-neutral">{t.timezone}</span>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {new Date(t.created_at).toLocaleString()}
                  </td>
                  <td>
                    <code style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.id}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid-3" style={{ marginBottom: 28 }}>
        <Card title={<><Database size={18} /> Tenant Model Schema</>} subtitle="Table: tenants">
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: 8 }}>
            <div><strong>Primary Key:</strong> <code style={{ color: '#38bdf8' }}>id UUID PRIMARY KEY</code></div>
            <div><strong>Attributes:</strong> <code style={{ color: '#38bdf8' }}>name VARCHAR(255)</code></div>
            <div><strong>Domain:</strong> <code style={{ color: '#38bdf8' }}>domain VARCHAR(255) UNIQUE</code></div>
            <div><strong>Timestamps:</strong> <code style={{ color: '#38bdf8' }}>created_at, updated_at</code></div>
          </div>
        </Card>

        <Card title={<><ShieldCheck size={18} /> Physical Tenant Isolation</>} subtitle="PostgreSQL Engine Level">
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: 8 }}>
            <div><strong>Composite Foreign Keys:</strong></div>
            <ul style={{ paddingLeft: 18, marginTop: 4 }}>
              <li><code>fk_orders_customer_tenant</code></li>
              <li><code>fk_order_items_order_tenant</code></li>
              <li><code>fk_order_items_product_tenant</code></li>
            </ul>
          </div>
        </Card>

        <Card title={<><KeyRound size={18} /> Tenant-Aware Uniqueness</>} subtitle="Unique Constraints">
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginTop: 8 }}>
            <div>Customer email unique per tenant: <code>(tenant_id, email)</code></div>
            <div>Product SKU unique per tenant: <code>(tenant_id, sku)</code></div>
            <div>External Order ID: <code>(tenant_id, external_order_id)</code></div>
          </div>
        </Card>
      </div>
    </div>
  )
}

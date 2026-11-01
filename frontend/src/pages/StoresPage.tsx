import React from 'react'
import { Store, ShieldCheck, Database, KeyRound, AlertCircle } from 'lucide-react'
import { Card } from '../components/common/Card'
import { StatusBadge } from '../components/common/StatusBadge'

export const StoresPage: React.FC = () => {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <Store size={26} style={{ color: 'var(--accent-primary)' }} />
          Tenant Store Management
        </h1>
        <p className="page-description">
          Multi-tenant store isolation topology and tenant identification schema
        </p>
      </div>

      <div style={{
        backgroundColor: 'rgba(245, 158, 11, 0.08)',
        border: '1px solid rgba(245, 158, 11, 0.25)',
        borderRadius: 'var(--radius-md)',
        padding: '16px 20px',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 14,
      }}>
        <AlertCircle size={20} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 2 }} />
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
            Tenant Store Data Service Pending Stage 4 API Integration
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.5 }}>
            Store listing endpoints (<code style={{ color: '#38bdf8' }}>/api/v1/analytics/manager/stores</code>) and store creation workflows require authentication and user-to-tenant mapping routes. Below is the active schema contract verified in migration <code style={{ color: '#38bdf8' }}>0001_initial_schema.py</code>.
          </div>
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

      <div className="card">
        <h3 className="card-title">Tenant Store Integration Roadmap</h3>
        <div className="table-wrapper" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th>Target Endpoint</th>
                <th>Required Role</th>
                <th>Integration Stage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>List Authorized Stores</td>
                <td><code>GET /api/v1/analytics/manager/stores</code></td>
                <td>Manager / Admin</td>
                <td>Stage 4 Backend API</td>
                <td><StatusBadge status="planned" /></td>
              </tr>
              <tr>
                <td>Active Tenant Resolution</td>
                <td><code>GET /api/v1/auth/me</code></td>
                <td>Merchant / Manager</td>
                <td>Stage 4 RBAC</td>
                <td><StatusBadge status="planned" /></td>
              </tr>
              <tr>
                <td>Cross-Tenant Store Compare</td>
                <td><code>GET /api/v1/analytics/manager/compare</code></td>
                <td>Manager</td>
                <td>Stage 4 Aggregation</td>
                <td><StatusBadge status="planned" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}


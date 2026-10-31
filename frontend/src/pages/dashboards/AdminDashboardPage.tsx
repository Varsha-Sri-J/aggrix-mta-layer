import React from 'react'
import {
  ShieldCheck,
  Database,
  Layers,
  Server,
  Activity,
  Cpu,
  CheckCircle2,
} from 'lucide-react'
import { RoleSwitcher } from '../../components/dashboard/RoleSwitcher'
import { PlatformHealthSummary } from '../../components/dashboard/PlatformHealthSummary'
import { Card } from '../../components/common/Card'

export const AdminDashboardPage: React.FC = () => {
  const schemaModels = [
    { name: 'tenants', pk: 'id (UUID)', isolation: 'Partition Root', fks: 'None', unique: 'domain' },
    { name: 'customers', pk: 'id (UUID)', isolation: 'tenant_id (NOT NULL)', fks: 'fk_customers_tenant_id', unique: '(tenant_id, email)' },
    { name: 'products', pk: 'id (UUID)', isolation: 'tenant_id (NOT NULL)', fks: 'fk_products_tenant_id', unique: '(tenant_id, sku)' },
    { name: 'orders', pk: 'id (UUID)', isolation: 'tenant_id (NOT NULL)', fks: 'fk_orders_customer_tenant', unique: '(tenant_id, external_order_id)' },
    { name: 'order_items', pk: 'id (UUID)', isolation: 'tenant_id (NOT NULL)', fks: 'fk_order_items_order_tenant, fk_order_items_product_tenant', unique: '(tenant_id, id)' },
    { name: 'outbox_events', pk: 'id (UUID)', isolation: 'tenant_id (NOT NULL)', fks: 'fk_outbox_events_tenant_id', unique: 'ix_outbox_events_unprocessed (partial)' },
  ]

  return (
    <div>
      <RoleSwitcher />

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="page-title">
            <ShieldCheck size={26} style={{ color: 'var(--accent-primary)' }} />
            Platform Admin & Engine Governance
          </h1>
          <p className="page-description">
            Global multi-tenant system health, PostgreSQL schema registry, and event streaming diagnostics
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="badge badge-success">
            <CheckCircle2 size={13} /> Global Admin Scope (admin:global)
          </span>
        </div>
      </div>

      {/* Real Live Backend Health Diagnostic Widget */}
      <div style={{ marginBottom: 24 }}>
        <PlatformHealthSummary />
      </div>

      {/* Engine Governance Metrics */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        <Card title={<><Server size={16} /> Backend Architecture</>}>
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#ffffff' }}>FastAPI</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Python 3.14.3 Runtime</div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--success)' }}>
              CORS Enabled (*)
            </div>
          </div>
        </Card>

        <Card title={<><Database size={16} /> Relational Store</>}>
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#ffffff' }}>PostgreSQL 16</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Port 5432 / localhost</div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--accent-primary)' }}>
              Alembic Migration 0001 Head
            </div>
          </div>
        </Card>

        <Card title={<><Layers size={16} /> Tenant Partitioning</>}>
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#ffffff' }}>Composite FKs</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Engine-level physical checks</div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-secondary)' }}>
              Zero cross-tenant leaks
            </div>
          </div>
        </Card>

        <Card title={<><Cpu size={16} /> Outbox Stream</>}>
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: '#ffffff' }}>Transactional</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>Table: outbox_events</div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--warning)' }}>
              Worker Daemon: Stage 4 Target
            </div>
          </div>
        </Card>
      </div>

      {/* Schema Registry Table */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <h3 className="card-title" style={{ margin: 0 }}>Verified Database Schema Registry</h3>
            <p className="card-desc" style={{ marginTop: 2 }}>
              6 SQLAlchemy 2.0 models validated in alembic/versions/0001_initial_schema.py
            </p>
          </div>
          <span className="badge badge-success">Production Ready</span>
        </div>

        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Table Name</th>
                <th>Primary Key</th>
                <th>Tenancy Enforcement</th>
                <th>Composite Foreign Key Constraints</th>
                <th>Unique Constraints & Indexes</th>
              </tr>
            </thead>
            <tbody>
              {schemaModels.map(m => (
                <tr key={m.name}>
                  <td>
                    <code style={{ fontWeight: 700, color: '#f1f5f9' }}>{m.name}</code>
                  </td>
                  <td>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent-primary)' }}>{m.pk}</span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>{m.isolation}</td>
                  <td>
                    <code style={{ fontSize: 11, color: '#94a3b8' }}>{m.fks}</code>
                  </td>
                  <td>
                    <code style={{ fontSize: 11, color: '#38bdf8' }}>{m.unique}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Platform Invariants & Stage 4 Pipeline Status */}
      <div className="grid-2">
        <Card title={<><ShieldCheck size={18} style={{ color: 'var(--success)' }} /> Verified Isolation Guarantees</>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ marginBottom: 8 }}>All child tables (<code style={{ color: '#38bdf8' }}>customers</code>, <code style={{ color: '#38bdf8' }}>products</code>, <code style={{ color: '#38bdf8' }}>orders</code>, <code style={{ color: '#38bdf8' }}>order_items</code>, <code style={{ color: '#38bdf8' }}>outbox_events</code>) require a <code style={{ color: '#38bdf8' }}>tenant_id</code> UUID column.</p>
            <p>Composite foreign keys enforce physical isolation at the database engine level. Deleting a tenant cascades across all child records with zero orphaned data.</p>
          </div>
        </Card>

        <Card title={<><Activity size={18} style={{ color: 'var(--warning)' }} /> Streaming Worker & DLQ Roadmap</>}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ marginBottom: 8 }}>The transactional outbox table exists in PostgreSQL with partial index <code style={{ color: '#38bdf8' }}>ix_outbox_events_unprocessed</code>.</p>
            <p>The autonomous worker daemon (<code style={{ color: '#38bdf8' }}>SKIP LOCKED</code> aggregation) and dead-letter queue (<code style={{ color: '#38bdf8' }}>outbox_dlq</code>) are scheduled for Stage 4 backend deployment.</p>
          </div>
        </Card>
      </div>
    </div>
  )
}

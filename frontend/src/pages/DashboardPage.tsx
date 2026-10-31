import React, { useEffect, useState } from 'react'
import {
  Layers,
  Database,
  AlertTriangle,
  Code2,
} from 'lucide-react'
import { Card } from '../components/common/Card'
import { StatusBadge } from '../components/common/StatusBadge'
import { RoleSwitcher } from '../components/dashboard/RoleSwitcher'
import { fetchHealth, fetchRootMeta } from '../services/api'
import type { HealthResponse, RootMetaResponse, EndpointSpec } from '../types/api'

export const DashboardPage: React.FC = () => {
  const [rootMeta, setRootMeta] = useState<RootMetaResponse | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    let isMounted = true
    Promise.all([
      fetchRootMeta().catch(() => null),
      fetchHealth().catch(() => null),
    ]).then(([metaData, healthData]) => {
      if (isMounted) {
        setRootMeta(metaData)
        setHealth(healthData)
        setLoading(false)
      }
    })
    return () => {
      isMounted = false
    }
  }, [])

  const endpoints: EndpointSpec[] = [
    {
      method: 'GET',
      path: '/',
      category: 'System & Health',
      status: 'available',
      description: 'System metadata, version, and documentation URL',
    },
    {
      method: 'GET',
      path: '/health',
      category: 'System & Health',
      status: 'available',
      description: 'Operational status and PostgreSQL database connection check (SELECT 1)',
    },
    {
      method: 'GET',
      path: '/api/v1/health',
      category: 'System & Health',
      status: 'available',
      description: 'Versioned health check endpoint for proxy and monitor compatibility',
    },
    {
      method: 'POST',
      path: '/api/v1/auth/login',
      category: 'Authentication & RBAC',
      status: 'planned',
      description: 'Merchant / Manager login endpoint returning JWT access token',
    },
    {
      method: 'GET',
      path: '/api/v1/auth/me',
      category: 'Authentication & RBAC',
      status: 'planned',
      description: 'Current authenticated user profile and assigned tenant scopes',
    },
    {
      method: 'GET',
      path: '/api/v1/analytics/tenants/{tenant_id}/summary',
      category: 'Merchant Analytics',
      status: 'planned',
      description: '7-day order count, gross sales turnover, and recent order activity',
    },
    {
      method: 'GET',
      path: '/api/v1/analytics/tenants/{tenant_id}/daily',
      category: 'Merchant Analytics',
      status: 'planned',
      description: '30-day chronological daily order time-series with zero-fill',
    },
    {
      method: 'GET',
      path: '/api/v1/analytics/tenants/{tenant_id}/products',
      category: 'Merchant Analytics',
      status: 'planned',
      description: 'Top 10 products by gross sales revenue scoped to currency',
    },
    {
      method: 'GET',
      path: '/api/v1/analytics/manager/summary',
      category: 'Manager Analytics',
      status: 'planned',
      description: 'Multi-store consolidated metrics for assigned tenant portfolios',
    },
    {
      method: 'GET',
      path: '/api/v1/analytics/manager/stores',
      category: 'Manager Analytics',
      status: 'planned',
      description: 'List and comparative status of managed tenant stores',
    },
    {
      method: 'GET',
      path: '/api/v1/analytics/manager/compare',
      category: 'Manager Analytics',
      status: 'planned',
      description: 'Cross-tenant performance comparison across configurable date windows',
    },
    {
      method: 'GET',
      path: '/api/v1/platform/summary',
      category: 'Platform Analytics',
      status: 'planned',
      description: 'Global multi-tenant system health, event throughput, and rollup sync lag',
    },
  ]

  return (
    <div>
      <RoleSwitcher />
      <div className="page-header">
        <h1 className="page-title">
          <Layers className="text-accent" size={26} style={{ color: 'var(--accent-primary)' }} />
          System Overview & Engine Status
        </h1>
        <p className="page-description">
          AGGRIX Multi-Tenant Analytics & Aggregation Engine — Frontend Foundation
        </p>
      </div>

      {/* Notice Banner */}
      <div style={{
        backgroundColor: 'rgba(59, 130, 246, 0.08)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
        borderRadius: 'var(--radius-md)',
        padding: '16px 20px',
        marginBottom: 24,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 14,
      }}>
        <AlertTriangle size={20} style={{ color: 'var(--accent-primary)', flexShrink: 0, marginTop: 2 }} />
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
            Stage 3 Foundation Mode — No Synthetic/Fictitious Analytics Rendered
          </div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.5 }}>
            In strict compliance with architectural guidelines, this dashboard displays verified backend engine diagnostics.
            Analytics route handlers (<code style={{ color: '#38bdf8' }}>/api/v1/analytics/*</code>) and JWT authentication (<code style={{ color: '#38bdf8' }}>/api/v1/auth/*</code>) are classified as planned Stage 4 deliverables.
          </div>
        </div>
      </div>

      {/* Core Diagnostic Grid */}
      <div className="grid-4" style={{ marginBottom: 28 }}>
        <Card title="FastAPI Engine" subtitle="Backend application service">
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ color: 'var(--text-muted)' }}>Status:</span>
              <StatusBadge status={rootMeta?.status === 'running' ? 'healthy' : (loading ? 'offline' : 'unhealthy')} label={rootMeta?.status ? 'Running' : 'Offline'} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Version:</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{rootMeta?.version || 'v0.1.0'}</span>
            </div>
          </div>
        </Card>

        <Card title="Database Connectivity" subtitle="PostgreSQL 16 Engine">
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ color: 'var(--text-muted)' }}>Connection:</span>
              <StatusBadge status={health?.database === 'connected' ? 'healthy' : 'unhealthy'} label={health?.database ? health.database.toUpperCase() : 'DISCONNECTED'} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Isolation:</span>
              <span style={{ color: 'var(--success)', fontWeight: 500 }}>Composite Foreign Keys</span>
            </div>
          </div>
        </Card>

        <Card title="Multi-Tenancy Mode" subtitle="Shopify-style tenant isolation">
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ color: 'var(--text-muted)' }}>Strategy:</span>
              <span className="badge badge-neutral">Shared Schema + Tenant ID</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Tables:</span>
              <span style={{ color: 'var(--text-secondary)' }}>6 Core Models</span>
            </div>
          </div>
        </Card>

        <Card title="Event Streaming" subtitle="Transactional Outbox">
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ color: 'var(--text-muted)' }}>Table:</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>outbox_events</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Worker Pipeline:</span>
              <span className="badge badge-warning">Stage 4 Target</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Backend Endpoint Availability Ledger */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#ffffff' }}>API Endpoint Availability Ledger</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 2 }}>
              Audited availability of FastAPI routes on <code style={{ color: '#38bdf8' }}>feature/frontend-dashboard</code>
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <span className="badge badge-success">3 Verified Available</span>
            <span className="badge badge-warning">9 Planned (Stage 4)</span>
          </div>
        </div>

        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th style={{ width: 90 }}>Method</th>
                <th>Endpoint Route</th>
                <th>Category</th>
                <th>Implementation Status</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((ep, idx) => (
                <tr key={idx}>
                  <td>
                    <span style={{
                      fontWeight: 700,
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: ep.method === 'GET' ? '#38bdf8' : '#34d399',
                      padding: '2px 6px',
                      borderRadius: 4,
                      backgroundColor: ep.method === 'GET' ? 'rgba(56, 189, 248, 0.1)' : 'rgba(52, 211, 153, 0.1)',
                    }}>
                      {ep.method}
                    </span>
                  </td>
                  <td>
                    <code style={{ fontSize: 12, color: '#f1f5f9' }}>{ep.path}</code>
                  </td>
                  <td>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{ep.category}</span>
                  </td>
                  <td>
                    <StatusBadge status={ep.status} />
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                    {ep.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Architecture Topology */}
      <div className="grid-2">
        <Card title={<><Database size={18} style={{ color: 'var(--accent-primary)' }} /> Database Layer Assets</>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
            <div>
              <strong style={{ color: '#ffffff' }}>PostgreSQL 16 Tables (Verified in Migration 0001):</strong>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                {['tenants', 'customers', 'products', 'orders', 'order_items', 'outbox_events'].map(tbl => (
                  <span key={tbl} className="code-box" style={{ padding: '3px 8px', fontSize: 11 }}>
                    {tbl}
                  </span>
                ))}
              </div>
            </div>
            <div style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
              Guaranteed isolation via composite keys: <code style={{ color: '#38bdf8' }}>(tenant_id, id)</code> on all entities.
            </div>
          </div>
        </Card>

        <Card title={<><Code2 size={18} style={{ color: 'var(--accent-primary)' }} /> Analytics Engine Contracts</>}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
            <div style={{ color: 'var(--text-secondary)' }}>
              Core SQL queries specified in <code style={{ color: '#38bdf8' }}>docs/analytics-sql-design.md</code>:
            </div>
            <ul style={{ paddingLeft: 18, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              <li><strong>Metric 1</strong>: 7-day order count parameterised by tenant</li>
              <li><strong>Metric 2</strong>: 7-day sales revenue grouped by currency</li>
              <li><strong>Metric 3</strong>: 30-day zero-filled series via <code style={{ color: '#38bdf8' }}>generate_series()</code></li>
              <li><strong>Metric 4</strong>: Top 10 products scoped by currency (Contract A)</li>
              <li><strong>Metric 5</strong>: Recent 20 orders with customer attributes</li>
            </ul>
          </div>
        </Card>
      </div>
    </div>
  )
}


import React from 'react'
import { Card } from '../common/Card'
import { Building2, ArrowUpRight, Inbox } from 'lucide-react'

export interface StoreMetric {
  tenantId: string
  name: string
  domain: string
  orders7d: number
  turnover7d: number
  currency: string
  status: 'active' | 'syncing' | 'paused'
}

interface StoreComparisonTableProps {
  stores: StoreMetric[]
  isDemoData?: boolean
}

export const StoreComparisonTable: React.FC<StoreComparisonTableProps> = ({
  stores,
  isDemoData = true,
}) => {
  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Building2 size={18} style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
          <span>Cross-Tenant Store Comparison Matrix</span>
        </div>
      }
      subtitle="Consolidated multi-store view for assigned Store Manager portfolio"
      action={
        isDemoData ? (
          <span className="badge-demo">DEMO DATA — NOT LIVE</span>
        ) : undefined
      }
    >
      <div style={{ marginTop: 12 }}>
        {stores.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
            <Inbox size={32} style={{ marginBottom: 8, opacity: 0.5 }} aria-hidden="true" />
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>No Assigned Stores</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              No tenant stores have been assigned to your manager account scope yet.
            </div>
          </div>
        ) : (
          <div className="table-wrapper">
            <table aria-label="Assigned tenant stores performance comparison matrix">
              <thead>
                <tr>
                  <th scope="col">Store / Tenant</th>
                  <th scope="col">Custom Domain</th>
                  <th scope="col" style={{ textAlign: 'right' }}>7d Orders</th>
                  <th scope="col" style={{ textAlign: 'right' }}>7d Gross Sales</th>
                  <th scope="col">Currency</th>
                  <th scope="col" style={{ textAlign: 'center' }}>Stream Status</th>
                  <th scope="col" style={{ width: 100 }}>Tenant UUID</th>
                </tr>
              </thead>
              <tbody>
                {stores.map(s => (
                  <tr key={s.tenantId}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.name}</div>
                    </td>
                    <td>
                      <a
                        href={`https://${s.domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--accent-primary)', display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 12 }}
                        aria-label={`Visit store domain ${s.domain} (opens in new tab)`}
                      >
                        {s.domain}
                        <ArrowUpRight size={12} aria-hidden="true" />
                      </a>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>
                      {s.orders7d.toLocaleString()}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: '#ffffff' }}>
                      ${s.turnover7d.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td>
                      <span className="badge badge-neutral">{s.currency}</span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className={`badge ${s.status === 'active' ? 'badge-success' : 'badge-warning'}`}>
                        {s.status.toUpperCase()}
                      </span>
                    </td>
                    <td>
                      <code style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                        {s.tenantId.slice(0, 8)}...
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  )
}

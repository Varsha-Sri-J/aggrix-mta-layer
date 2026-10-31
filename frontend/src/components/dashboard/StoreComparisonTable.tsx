import React from 'react'
import { Card } from '../common/Card'
import { Building2, ArrowUpRight } from 'lucide-react'

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
          <Building2 size={18} style={{ color: 'var(--accent-primary)' }} />
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
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Store / Tenant</th>
                <th>Custom Domain</th>
                <th style={{ textAlign: 'right' }}>7d Orders</th>
                <th style={{ textAlign: 'right' }}>7d Gross Sales</th>
                <th>Currency</th>
                <th style={{ textAlign: 'center' }}>Stream Status</th>
                <th style={{ width: 100 }}>Tenant UUID</th>
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
                    >
                      {s.domain}
                      <ArrowUpRight size={12} />
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
      </div>
    </Card>
  )
}

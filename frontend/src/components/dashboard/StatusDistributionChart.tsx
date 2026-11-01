import React from 'react'
import { Card } from '../common/Card'
import { PieChart } from 'lucide-react'

export interface StatusCount {
  status: 'paid' | 'fulfilled' | 'pending' | 'cancelled'
  label: string
  count: number
  color: string
}

interface StatusDistributionChartProps {
  data: StatusCount[]
  isDemoData?: boolean
}

export const StatusDistributionChart: React.FC<StatusDistributionChartProps> = ({
  data,
  isDemoData = false,
}) => {
  const total = data.reduce((acc, curr) => acc + curr.count, 0)

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <PieChart size={18} style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
          <span>Order Status Distribution</span>
        </div>
      }
      subtitle="Provisional sales recognition: 'paid' and 'fulfilled' contribute to turnover"
      action={
        isDemoData ? (
          <span className="badge-demo">DEMO DATA</span>
        ) : (
          <span
            className="badge badge-neutral"
            style={{ fontSize: 10, padding: '2px 7px' }}
            title="Aggregated order lifecycle statuses from PostgreSQL"
          >
            POSTGRESQL-BACKED
          </span>
        )
      }
    >
      <div style={{ marginTop: 8 }} role="region" aria-label="Order status breakdown visualization">
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--text-muted)' }}>
          <span>Total Orders Sample:</span>
          <strong style={{ color: '#ffffff' }}>{total}</strong>
        </div>

        {/* Multi-segment distribution bar */}
        <div
          className="dist-bar-track"
          role="progressbar"
          aria-label="Order status proportion"
          aria-valuenow={total}
          aria-valuemin={0}
          aria-valuemax={total}
        >
          {data.map(item => {
            const pct = total > 0 ? (item.count / total) * 100 : 0
            return (
              <div
                key={item.status}
                className="dist-bar-segment"
                style={{
                  width: `${pct}%`,
                  backgroundColor: item.color,
                }}
                title={`${item.label}: ${item.count} (${pct.toFixed(1)}%)`}
              />
            )
          })}
        </div>

        {/* Legend */}
        <div className="dist-legend">
          {data.map(item => {
            const pct = total > 0 ? ((item.count / total) * 100).toFixed(1) : '0'
            return (
              <div key={item.status} className="dist-legend-item">
                <span
                  className="dist-color-dot"
                  style={{ backgroundColor: item.color }}
                  aria-hidden="true"
                />
                <div>
                  <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                    {item.label}
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                    {item.count} orders ({pct}%)
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}

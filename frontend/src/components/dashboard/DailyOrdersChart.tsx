import React, { useState } from 'react'
import { Card } from '../common/Card'
import { Calendar } from 'lucide-react'

export interface DailyPoint {
  date: string
  orderCount: number
}

interface DailyOrdersChartProps {
  data: DailyPoint[]
  isDemoData?: boolean
}

export const DailyOrdersChart: React.FC<DailyOrdersChartProps> = ({
  data,
  isDemoData = false,
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<DailyPoint | null>(null)

  const maxCount = Math.max(...data.map(d => d.orderCount), 10)
  const chartHeight = 180
  const chartWidth = 720
  const barWidth = 14
  const gap = (chartWidth - data.length * barWidth) / (data.length - 1 || 1)
  const totalOrders = data.reduce((sum, d) => sum + d.orderCount, 0)

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Calendar size={18} style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
          <span>30-Day Daily Order Volume</span>
        </div>
      }
      subtitle="Chronological volume series aggregated from daily_tenant_metrics"
      action={
        isDemoData ? (
          <span className="badge-demo">DEMO DATA</span>
        ) : (
          <span
            className="badge badge-neutral"
            style={{ fontSize: 10, padding: '2px 7px' }}
            title="Precomputed daily rollups from PostgreSQL daily_tenant_metrics"
          >
            POSTGRESQL-BACKED
          </span>
        )
      }
    >
      <div style={{ position: 'relative', marginTop: 12 }}>
        {/* Screen Reader Summary */}
        <div className="sr-only">
          <p>
            30-day order volume summary. Total orders across this period: {totalOrders}.
            Highest single-day volume: {maxCount} orders.
          </p>
        </div>

        {hoveredPoint && (
          <div
            role="status"
            aria-live="polite"
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              padding: '6px 12px',
              borderRadius: 'var(--radius-sm)',
              fontSize: 12,
              zIndex: 10,
              display: 'flex',
              gap: 8,
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.4)',
            }}
          >
            <span style={{ color: 'var(--text-muted)' }}>Date: <strong style={{ color: '#ffffff' }}>{hoveredPoint.date}</strong></span>
            <span style={{ color: 'var(--accent-primary)' }}>Orders: <strong>{hoveredPoint.orderCount}</strong></span>
          </div>
        )}

        <div className="svg-chart-container">
          <svg
            viewBox={`0 0 ${chartWidth} ${chartHeight + 35}`}
            role="img"
            aria-label={`30-day order volume bar chart with ${data.length} dates, totaling ${totalOrders} orders.`}
            style={{ width: '100%', height: 'auto', display: 'block' }}
          >
            <title>30-Day Daily Order Volume Chart</title>
            <desc>Displays daily order count across 30 chronological days with zero-fill support.</desc>

            {/* Horizontal Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct, idx) => {
              const y = chartHeight - pct * chartHeight + 10
              const label = Math.round(pct * maxCount)
              return (
                <g key={idx} aria-hidden="true">
                  <line
                    x1="0"
                    y1={y}
                    x2={chartWidth}
                    y2={y}
                    className="chart-grid-line"
                  />
                  <text
                    x="2"
                    y={y - 4}
                    className="chart-axis-text"
                  >
                    {label}
                  </text>
                </g>
              )
            })}

            {/* Bars */}
            {data.map((d, idx) => {
              const barHeight = (d.orderCount / maxCount) * chartHeight
              const x = idx * (barWidth + gap)
              const y = chartHeight - barHeight + 10

              return (
                <g
                  key={d.date}
                  tabIndex={0}
                  role="graphics-symbol"
                  aria-label={`${d.date}: ${d.orderCount} orders`}
                  onMouseEnter={() => setHoveredPoint(d)}
                  onMouseLeave={() => setHoveredPoint(null)}
                  onFocus={() => setHoveredPoint(d)}
                  onBlur={() => setHoveredPoint(null)}
                  style={{ outline: 'none' }}
                >
                  <rect
                    x={x}
                    y={y}
                    width={barWidth}
                    height={Math.max(barHeight, 2)}
                    rx="3"
                    className="chart-bar"
                    style={{
                      fill: hoveredPoint?.date === d.date ? '#60a5fa' : '#3b82f6',
                      opacity: d.orderCount === 0 ? 0.35 : 1,
                    }}
                  />
                  {/* Date labels on selected intervals */}
                  {idx % 5 === 0 && (
                    <text
                      x={x + barWidth / 2}
                      y={chartHeight + 28}
                      textAnchor="middle"
                      className="chart-axis-text"
                      aria-hidden="true"
                    >
                      {d.date.slice(5)}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, fontSize: 11, color: 'var(--text-muted)' }}>
          <span>Contract: Guaranteed 30 rows returned with zero-count fill</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
            Endpoint: GET /api/v1/analytics/tenants/:id/daily
          </span>
        </div>
      </div>
    </Card>
  )
}

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
  isDemoData = true,
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<DailyPoint | null>(null)

  const maxCount = Math.max(...data.map(d => d.orderCount), 10)
  const chartHeight = 180
  const chartWidth = 720
  const barWidth = 14
  const gap = (chartWidth - data.length * barWidth) / (data.length - 1 || 1)

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Calendar size={18} style={{ color: 'var(--accent-primary)' }} />
          <span>30-Day Daily Order Volume (Metric 3 Preview)</span>
        </div>
      }
      subtitle="Zero-filled chronological series generated via generate_series() contract"
      action={
        isDemoData ? (
          <span className="badge-demo">DEMO DATA — NOT LIVE</span>
        ) : undefined
      }
    >
      <div style={{ position: 'relative', marginTop: 12 }}>
        {hoveredPoint && (
          <div style={{
            position: 'absolute',
            top: 0,
            right: 0,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            padding: '4px 10px',
            borderRadius: 'var(--radius-sm)',
            fontSize: 12,
            zIndex: 10,
            display: 'flex',
            gap: 8,
          }}>
            <span style={{ color: 'var(--text-muted)' }}>Date: <strong style={{ color: '#ffffff' }}>{hoveredPoint.date}</strong></span>
            <span style={{ color: 'var(--accent-primary)' }}>Orders: <strong>{hoveredPoint.orderCount}</strong></span>
          </div>
        )}

        <div className="svg-chart-container">
          <svg
            viewBox={`0 0 ${chartWidth} ${chartHeight + 35}`}
            style={{ width: '100%', height: 'auto', display: 'block' }}
          >
            {/* Horizontal Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((pct, idx) => {
              const y = chartHeight - pct * chartHeight + 10
              const label = Math.round(pct * maxCount)
              return (
                <g key={idx}>
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
                  onMouseEnter={() => setHoveredPoint(d)}
                  onMouseLeave={() => setHoveredPoint(null)}
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

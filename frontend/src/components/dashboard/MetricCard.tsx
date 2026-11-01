import React from 'react'
import { TrendingUp, TrendingDown, Clock } from 'lucide-react'

export interface DataSourceBadge {
  text: string
  variant?: 'live' | 'seeded' | 'benchmark' | 'demo'
  title?: string
}

export interface MetricCardProps {
  title: string
  value: string | number
  unit?: string
  trend?: {
    percentage: number
    isPositive: boolean
    label: string
  }
  subtitle?: string
  isDemoData?: boolean
  dataSourceBadge?: DataSourceBadge
  backendEndpoint?: string
  icon?: React.ReactNode
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  unit,
  trend,
  subtitle,
  isDemoData = false,
  dataSourceBadge,
  backendEndpoint,
  icon,
}) => {
  const renderBadge = () => {
    if (dataSourceBadge) {
      let badgeClass = 'badge-demo'
      let customStyle: React.CSSProperties = {}

      switch (dataSourceBadge.variant) {
        case 'live':
          badgeClass = 'badge badge-success'
          customStyle = { fontSize: 10, padding: '2px 7px', fontWeight: 600 }
          break
        case 'seeded':
          badgeClass = 'badge'
          customStyle = {
            backgroundColor: 'rgba(56, 189, 248, 0.15)',
            color: '#38bdf8',
            border: '1px solid rgba(56, 189, 248, 0.4)',
            fontSize: 10,
            padding: '2px 7px',
            fontWeight: 600,
          }
          break
        case 'benchmark':
          badgeClass = 'badge'
          customStyle = {
            backgroundColor: 'rgba(168, 85, 247, 0.15)',
            color: '#c084fc',
            border: '1px solid rgba(168, 85, 247, 0.4)',
            fontSize: 10,
            padding: '2px 7px',
            fontWeight: 600,
          }
          break
        case 'demo':
        default:
          badgeClass = 'badge-demo'
          break
      }

      return (
        <span className={badgeClass} style={customStyle} title={dataSourceBadge.title}>
          {dataSourceBadge.text}
        </span>
      )
    }

    if (isDemoData) {
      return (
        <span className="badge-demo" title="Illustrative demo indicator">
          DEMO INDICATOR
        </span>
      )
    }

    return null
  }

  return (
    <div className="metric-card">
      <div className="metric-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && <span style={{ color: 'var(--accent-primary)' }}>{icon}</span>}
          <span className="metric-title">{title}</span>
        </div>
        {renderBadge()}
      </div>

      <div className="metric-value-box">
        <span className="metric-value">{value}</span>
        {unit && <span className="metric-unit">{unit}</span>}
      </div>

      {trend && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginBottom: 8 }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 2,
              fontWeight: 600,
              color: trend.isPositive ? 'var(--success)' : 'var(--danger)',
            }}
          >
            {trend.isPositive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
            {trend.isPositive ? `+${trend.percentage}%` : `${trend.percentage}%`}
          </span>
          <span style={{ color: 'var(--text-muted)' }}>{trend.label}</span>
        </div>
      )}

      {(subtitle || backendEndpoint) && (
        <div className="metric-footer">
          {subtitle && <span>{subtitle}</span>}
          {backendEndpoint && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)', fontSize: 11 }}>
              <Clock size={11} /> <code>{backendEndpoint}</code>
            </span>
          )}
        </div>
      )}
    </div>
  )
}


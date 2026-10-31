import React from 'react'
import { TrendingUp, TrendingDown, Clock } from 'lucide-react'

interface MetricCardProps {
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
  backendEndpoint?: string
  icon?: React.ReactNode
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  unit,
  trend,
  subtitle,
  isDemoData = true,
  backendEndpoint,
  icon,
}) => {
  return (
    <div className="metric-card">
      <div className="metric-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && <span style={{ color: 'var(--accent-primary)' }}>{icon}</span>}
          <span className="metric-title">{title}</span>
        </div>
        {isDemoData && (
          <span className="badge-demo" title="Demo preview data — awaiting Stage 4 backend API">
            DEMO DATA
          </span>
        )}
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


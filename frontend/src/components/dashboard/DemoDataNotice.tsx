import React from 'react'
import { AlertTriangle, Clock } from 'lucide-react'

interface DemoDataNoticeProps {
  endpoint: string
  metricTitle?: string
}

export const DemoDataNotice: React.FC<DemoDataNoticeProps> = ({
  endpoint,
  metricTitle,
}) => {
  return (
    <div className="demo-banner">
      <AlertTriangle size={18} style={{ color: '#fbbf24', flexShrink: 0, marginTop: 2 }} />
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="badge-demo">
            DEMO DATA — NOT LIVE
          </span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <Clock size={11} /> Awaiting Stage 4 Backend Route:
          </span>
          <code style={{ fontSize: 11, color: '#38bdf8' }}>{endpoint}</code>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 4, lineHeight: 1.5 }}>
          {metricTitle ? `The ${metricTitle} below is` : 'Metrics displayed below are'}{' '}
          representative preview data designed for UI evaluation. Real analytics aggregation requires upcoming Stage 4 FastAPI route implementation.
        </p>
      </div>
    </div>
  )
}


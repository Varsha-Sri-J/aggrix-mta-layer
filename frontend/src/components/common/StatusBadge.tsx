import React from 'react'
import { CheckCircle2, AlertCircle, Clock, XCircle } from 'lucide-react'
import type { EndpointStatus } from '../../types/api'

interface StatusBadgeProps {
  status: EndpointStatus | 'healthy' | 'unhealthy' | 'running'
  label?: string
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => {
  if (status === 'available' || status === 'healthy' || status === 'running') {
    return (
      <span className="badge badge-success">
        <CheckCircle2 size={12} />
        {label || (status === 'available' ? 'Available' : 'Healthy')}
      </span>
    )
  }

  if (status === 'planned') {
    return (
      <span className="badge badge-warning">
        <Clock size={12} />
        {label || 'Planned (Stage 4)'}
      </span>
    )
  }

  if (status === 'unhealthy') {
    return (
      <span className="badge badge-danger">
        <AlertCircle size={12} />
        {label || 'Unhealthy'}
      </span>
    )
  }

  return (
    <span className="badge badge-neutral">
      <XCircle size={12} />
      {label || 'Offline'}
    </span>
  )
}


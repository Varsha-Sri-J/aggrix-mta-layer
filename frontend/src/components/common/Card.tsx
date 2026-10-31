import React from 'react'

interface CardProps {
  title?: React.ReactNode
  subtitle?: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}

export const Card: React.FC<CardProps> = ({ title, subtitle, children, className = '', action }) => {
  return (
    <div className={`card ${className}`}>
      {(title || action) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-desc" style={{ marginTop: 2 }}>{subtitle}</p>}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      {children}
    </div>
  )
}


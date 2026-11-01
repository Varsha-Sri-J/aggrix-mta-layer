import React from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, ArrowLeft } from 'lucide-react'

export const NotFoundPage: React.FC = () => {
  return (
    <div style={{ textAlign: 'center', padding: '80px 20px' }}>
      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 64,
        height: 64,
        borderRadius: '50%',
        backgroundColor: 'var(--danger-bg)',
        color: 'var(--danger)',
        marginBottom: 20,
      }}>
        <AlertCircle size={32} />
      </div>
      <h1 style={{ fontSize: 28, fontWeight: 700, color: '#ffffff', marginBottom: 8 }}>Page Not Found</h1>
      <p style={{ color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto 24px' }}>
        The requested URL was not found in the AGGRIX frontend routing configuration.
      </p>
      <Link
        to="/"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          backgroundColor: 'var(--accent-primary)',
          color: '#ffffff',
          padding: '10px 20px',
          borderRadius: 'var(--radius-sm)',
          fontWeight: 600,
          fontSize: 13,
        }}
      >
        <ArrowLeft size={16} />
        Back to Dashboard Overview
      </Link>
    </div>
  )
}


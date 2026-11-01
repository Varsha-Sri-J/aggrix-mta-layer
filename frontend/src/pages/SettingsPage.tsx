import React from 'react'
import { Settings, Sliders, Shield, Terminal } from 'lucide-react'
import { Card } from '../components/common/Card'
import { env } from '../config/env'

export const SettingsPage: React.FC = () => {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <Settings size={26} style={{ color: 'var(--accent-primary)' }} />
          System Settings & Environment
        </h1>
        <p className="page-description">
          Runtime configuration, client variables, and build parameters
        </p>
      </div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        <Card title={<><Sliders size={18} /> Frontend Environment Configuration</>}>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12, fontSize: 13 }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>VITE_API_BASE_URL:</span>
              <div className="code-box" style={{ marginTop: 4 }}>{env.apiBaseUrl}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>VITE_APP_ENV:</span>
              <div className="code-box" style={{ marginTop: 4 }}>{env.appEnv}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Runtime Mode:</span>
              <div style={{ marginTop: 4 }}>
                <span className="badge badge-neutral">{env.isDev ? 'Development (Hot Reloading)' : 'Production Bundle'}</span>
              </div>
            </div>
          </div>
        </Card>

        <Card title={<><Shield size={18} /> Security & CORS Guidelines</>}>
          <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            <p style={{ marginBottom: 10 }}>The FastAPI backend applies <code style={{ color: '#38bdf8' }}>CORSMiddleware</code> to accept cross-origin requests from frontend clients.</p>
            <p style={{ marginBottom: 10 }}>In production environments, restrict <code style={{ color: '#38bdf8' }}>allow_origins</code> in <code style={{ color: '#38bdf8' }}>backend/app/main.py</code> to verified domain names rather than wildcard <code style={{ color: '#38bdf8' }}>"*"</code>.</p>
            <p>Authentication credentials will be securely transmitted via <code style={{ color: '#38bdf8' }}>Authorization: Bearer &lt;JWT&gt;</code> headers once Stage 4 auth is active.</p>
          </div>
        </Card>
      </div>

      <Card title={<><Terminal size={18} /> Development Scripts</>}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginTop: 12 }}>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>Start Dev Server</div>
            <div className="code-box">npm run dev</div>
          </div>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>Production Build</div>
            <div className="code-box">npm run build</div>
          </div>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>Type Check</div>
            <div className="code-box">npm run lint</div>
          </div>
        </div>
      </Card>
    </div>
  )
}


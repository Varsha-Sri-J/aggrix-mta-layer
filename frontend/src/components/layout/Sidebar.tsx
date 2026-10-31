import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Store,
  BarChart3,
  Activity,
  Settings,
  Layers,
  KeyRound,
  Building2,
  ShieldCheck,
  X,
} from 'lucide-react'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  return (
    <aside
      id="app-sidebar"
      className={`app-sidebar ${isOpen ? 'open' : ''}`}
      role="navigation"
      aria-label="Main Application Navigation"
    >
      <div className="sidebar-header">
        <div className="brand-badge">
          <div className="brand-icon-box" aria-hidden="true">
            <Layers size={18} />
          </div>
          <div>
            <div className="brand-title">AGGRIX</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <span className="brand-tag">MTA Engine</span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>v0.1.0</span>
            </div>
          </div>
        </div>
        <button
          className="menu-trigger"
          onClick={onClose}
          aria-label="Close navigation sidebar"
          style={{ display: isOpen ? 'block' : 'none' }}
        >
          <X size={20} aria-hidden="true" />
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Sidebar Menu Links">
        <div className="nav-section-title">Role Dashboards</div>
        <NavLink
          to="/dashboard/merchant"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <Store size={18} aria-hidden="true" />
          <span>Merchant Dashboard</span>
        </NavLink>

        <NavLink
          to="/dashboard/manager"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <Building2 size={18} aria-hidden="true" />
          <span>Manager Dashboard</span>
        </NavLink>

        <NavLink
          to="/dashboard/admin"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <ShieldCheck size={18} aria-hidden="true" />
          <span>Platform Admin</span>
        </NavLink>

        <div className="nav-section-title">Operations</div>
        <NavLink
          to="/"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <LayoutDashboard size={18} aria-hidden="true" />
          <span>Overview Ledger</span>
        </NavLink>

        <NavLink
          to="/stores"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <Store size={18} aria-hidden="true" />
          <span>Tenant Stores</span>
        </NavLink>

        <div className="nav-section-title">Analytics & Intelligence</div>
        <NavLink
          to="/analytics"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <BarChart3 size={18} aria-hidden="true" />
          <span>Analytics Engine</span>
        </NavLink>

        <div className="nav-section-title">System & Infrastructure</div>
        <NavLink
          to="/health"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <Activity size={18} aria-hidden="true" />
          <span>Health Diagnostics</span>
        </NavLink>

        <NavLink
          to="/settings"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <Settings size={18} aria-hidden="true" />
          <span>System Settings</span>
        </NavLink>

        <div className="nav-section-title">Security & Access</div>
        <NavLink
          to="/login"
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          onClick={onClose}
        >
          <KeyRound size={18} aria-hidden="true" />
          <span>Auth & RBAC (Stage 4)</span>
        </NavLink>
      </nav>

      <div className="sidebar-footer">
        <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>AGGRIX MTA Layer</div>
        <div>Shopify-Inspired Multi-Tenancy</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
          Base: FastAPI + PostgreSQL 16
        </div>
      </div>
    </aside>
  )
}

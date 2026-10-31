import React from 'react'
import { NavLink } from 'react-router-dom'
import { Store, Building2, ShieldCheck } from 'lucide-react'

export const RoleSwitcher: React.FC = () => {
  return (
    <nav className="role-switcher-bar" role="navigation" aria-label="Dashboard Role Switcher">
      <NavLink
        to="/dashboard/merchant"
        className={({ isActive }) => `role-switch-btn ${isActive ? 'active' : ''}`}
        aria-label="Switch to Merchant / Tenant Dashboard"
      >
        <Store size={15} aria-hidden="true" />
        <span>1. Merchant / Tenant</span>
      </NavLink>

      <NavLink
        to="/dashboard/manager"
        className={({ isActive }) => `role-switch-btn ${isActive ? 'active' : ''}`}
        aria-label="Switch to Store Manager Dashboard"
      >
        <Building2 size={15} aria-hidden="true" />
        <span>2. Store Manager</span>
      </NavLink>

      <NavLink
        to="/dashboard/admin"
        className={({ isActive }) => `role-switch-btn ${isActive ? 'active' : ''}`}
        aria-label="Switch to Platform Admin Dashboard"
      >
        <ShieldCheck size={15} aria-hidden="true" />
        <span>3. Platform Admin</span>
      </NavLink>
    </nav>
  )
}

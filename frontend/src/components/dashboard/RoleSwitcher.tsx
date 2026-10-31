import React from 'react'
import { NavLink } from 'react-router-dom'
import { Store, Building2, ShieldCheck } from 'lucide-react'

export const RoleSwitcher: React.FC = () => {
  return (
    <div className="role-switcher-bar">
      <NavLink
        to="/dashboard/merchant"
        className={({ isActive }) => `role-switch-btn ${isActive ? 'active' : ''}`}
      >
        <Store size={15} />
        <span>1. Merchant / Tenant</span>
      </NavLink>

      <NavLink
        to="/dashboard/manager"
        className={({ isActive }) => `role-switch-btn ${isActive ? 'active' : ''}`}
      >
        <Building2 size={15} />
        <span>2. Store Manager</span>
      </NavLink>

      <NavLink
        to="/dashboard/admin"
        className={({ isActive }) => `role-switch-btn ${isActive ? 'active' : ''}`}
      >
        <ShieldCheck size={15} />
        <span>3. Platform Admin</span>
      </NavLink>
    </div>
  )
}

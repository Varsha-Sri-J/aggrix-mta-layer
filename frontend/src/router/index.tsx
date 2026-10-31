import React from 'react'
import { Routes, Route } from 'react-router-dom'
import { MainLayout } from '../components/layout/MainLayout'
import { DashboardPage } from '../pages/DashboardPage'
import { MerchantDashboardPage } from '../pages/dashboards/MerchantDashboardPage'
import { ManagerDashboardPage } from '../pages/dashboards/ManagerDashboardPage'
import { AdminDashboardPage } from '../pages/dashboards/AdminDashboardPage'
import { StoresPage } from '../pages/StoresPage'
import { AnalyticsPage } from '../pages/AnalyticsPage'
import { HealthPage } from '../pages/HealthPage'
import { SettingsPage } from '../pages/SettingsPage'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'

export const AppRouter: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="dashboard/merchant" element={<MerchantDashboardPage />} />
        <Route path="dashboard/manager" element={<ManagerDashboardPage />} />
        <Route path="dashboard/admin" element={<AdminDashboardPage />} />
        <Route path="stores" element={<StoresPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="health" element={<HealthPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}


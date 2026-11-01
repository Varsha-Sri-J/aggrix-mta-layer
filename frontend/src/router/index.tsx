import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
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
import { AccessDeniedPage } from '../pages/AccessDeniedPage'
import { ProtectedRoute } from '../components/auth/ProtectedRoute'
import { useAuth } from '../context/AuthContext'

const RootRedirect: React.FC = () => {
  const { user, isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return null
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />
  }

  if (user.role === 'admin') {
    return <Navigate to="/dashboard/admin" replace />
  }

  if (user.role === 'manager') {
    return <Navigate to="/dashboard/manager" replace />
  }

  return <Navigate to="/dashboard/merchant" replace />
}

export const AppRouter: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        {/* Dynamic Root Route */}
        <Route index element={<RootRedirect />} />

        {/* Role-Protected Dashboards */}
        <Route
          path="dashboard/merchant"
          element={
            <ProtectedRoute allowedRoles={['merchant', 'admin']}>
              <MerchantDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="dashboard/manager"
          element={
            <ProtectedRoute allowedRoles={['manager', 'admin']}>
              <ManagerDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="dashboard/admin"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage />
            </ProtectedRoute>
          }
        />

        {/* Protected Operations & Administration */}
        <Route
          path="stores"
          element={
            <ProtectedRoute allowedRoles={['merchant', 'manager', 'admin']}>
              <StoresPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="overview"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="settings"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <SettingsPage />
            </ProtectedRoute>
          }
        />

        {/* Informational & Security Routes */}
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="health" element={<HealthPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="unauthorized" element={<AccessDeniedPage />} />

        {/* 404 Fallback */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

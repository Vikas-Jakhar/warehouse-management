import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import RequireAuth from './components/RequireAuth'
import { AuthProvider } from './hooks/useAuth'
import AuditLogsPage from './pages/AuditLogsPage'
import DashboardPage from './pages/DashboardPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import SkusPage from './pages/SkusPage'
import WarehouseDataPage from './pages/WarehouseDataPage'
import WarehouseForecastingPage from './pages/WarehouseForecastingPage'
import WarehouseLayoutPage from './pages/WarehouseLayoutPage'
import WarehouseMovementsPage from './pages/WarehouseMovementsPage'
import WarehouseRecommendationsPage from './pages/WarehouseRecommendationsPage'
import WarehouseReportsPage from './pages/WarehouseReportsPage'
import WarehousesPage from './pages/WarehousesPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            <Route
              path="/app"
              element={
                <RequireAuth>
                  <AppShell />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="onboarding" element={<Navigate to="/app/dashboard" replace />} />
              <Route path="warehouses" element={<WarehousesPage />} />
              <Route path="warehouses/:warehouseId/layout" element={<WarehouseLayoutPage />} />
              <Route path="warehouses/:warehouseId/data" element={<WarehouseDataPage />} />
              <Route path="warehouses/:warehouseId/forecasting" element={<WarehouseForecastingPage />} />
              <Route path="warehouses/:warehouseId/recommendations" element={<WarehouseRecommendationsPage />} />
              <Route path="warehouses/:warehouseId/movements" element={<WarehouseMovementsPage />} />
              <Route path="warehouses/:warehouseId/reports" element={<WarehouseReportsPage />} />
              <Route path="skus" element={<SkusPage />} />
              <Route path="audit-logs" element={<AuditLogsPage />} />
              {/* onboarding, layout builder, SKUs, forecasting, recommendations,
                  movements, reports, users, settings land in later phases */}
            </Route>

            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

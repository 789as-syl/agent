import { Suspense, lazy } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AdminProtectedRoute, AdminPublicRoute } from './components/AdminProtectedRoute'

const AdminLayout = lazy(() => import('./components/AdminLayout'))
const AdminLoginPage = lazy(() => import('./pages/AdminLoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const KnowledgeManagementPage = lazy(() => import('./pages/KnowledgeManagementPage'))
const QuestionManagementPage = lazy(() => import('./pages/QuestionManagementPage'))
const KnowledgeGraphPage = lazy(() => import('./pages/KnowledgeGraphPage'))
const UserAccountManagementPage = lazy(() => import('./pages/UserAccountManagementPage'))
const UserSessionAuditPage = lazy(() => import('./pages/UserSessionAuditPage'))

const RouteFallback = () => <div className="min-h-screen bg-slate-50" />

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#6366f1',
          borderRadius: 8,
        },
      }}
    >
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3000,
          style: {
            background: '#363636',
            color: '#fff',
          },
        }}
      />
      <Router>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route element={<AdminPublicRoute />}>
              <Route path="/login" element={<AdminLoginPage />} />
            </Route>

            <Route element={<AdminProtectedRoute />}>
              <Route element={<AdminLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/knowledge" element={<KnowledgeManagementPage />} />
                <Route path="/questions" element={<QuestionManagementPage />} />
                <Route path="/graph" element={<KnowledgeGraphPage />} />
                <Route path="/users" element={<UserAccountManagementPage />} />
                <Route path="/user-sessions" element={<UserSessionAuditPage />} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Router>
    </ConfigProvider>
  )
}

export default App

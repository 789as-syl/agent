import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAdminAuthStore } from '../store'

export function AdminProtectedRoute() {
  const isAuthenticated = useAdminAuthStore((state) => state.isAuthenticated)
  const user = useAdminAuthStore((state) => state.user)
  const fetchMe = useAdminAuthStore((state) => state.fetchMe)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let active = true

    const run = async () => {
      try {
        // Always validate current session to avoid stale persisted auth state.
        await fetchMe()
      } catch {
        // handled in store
      }

      if (active) setChecking(false)
    }

    void run()
    return () => {
      active = false
    }
  }, [fetchMe])

  if (checking) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">会话校验中...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (!user || user.role !== 'admin') {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}

export function AdminPublicRoute() {
  const isAuthenticated = useAdminAuthStore((state) => state.isAuthenticated)
  const user = useAdminAuthStore((state) => state.user)

  if (isAuthenticated && user?.role === 'admin') {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

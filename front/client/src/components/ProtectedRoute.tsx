import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '../store'

export function ProtectedRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const fetchMe = useAuthStore((state) => state.fetchMe)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let active = true

    const run = async () => {
      try {
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

  return <Outlet />
}

export function PublicRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const user = useAuthStore((state) => state.user)

  if (isAuthenticated && user) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  BookOpen,
  FileQuestion,
  Network,
  LogOut,
  Menu,
  ChevronLeft,
  ChevronRight,
  Shield,
  Users,
  MessagesSquare,
} from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'
import { useAdminAuthStore, useAdminGlobalStore } from '../store'

const menuItems = [
  { path: '/', label: '数据看板', icon: LayoutDashboard },
  { path: '/knowledge', label: '知识库管理', icon: BookOpen },
  { path: '/questions', label: '题库管理', icon: FileQuestion },
  { path: '/graph', label: '知识图谱', icon: Network },
  { path: '/users', label: '用户账号管理', icon: Users },
  { path: '/user-sessions', label: '用户会话审阅', icon: MessagesSquare },
]

export default function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const user = useAdminAuthStore((state) => state.user)
  const logout = useAdminAuthStore((state) => state.logout)
  const sidebarCollapsed = useAdminGlobalStore((state) => state.sidebarCollapsed)
  const setSidebarCollapsed = useAdminGlobalStore((state) => state.setSidebarCollapsed)

  const handleLogout = async () => {
    try {
      await logout()
      navigate('/login')
      toast.success('已退出登录')
    } catch {
      toast.error('退出失败')
    }
  }

  return (
    <div className="flex h-screen bg-gray-100">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black bg-opacity-50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 bg-gradient-to-b from-slate-900 to-indigo-900 text-white transition-all duration-300 lg:static ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        } ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}
      >
        <div className="flex h-full flex-col">
          <div className="border-b border-white/10 p-4">
            <div className="flex items-center space-x-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-white/20">
                <Shield className="h-6 w-6" />
              </div>
              {!sidebarCollapsed && <span className="text-xl font-bold">管理后台</span>}
            </div>
          </div>

          <nav className="flex-1 space-y-2 p-4">
            {menuItems.map((item) => {
              const Icon = item.icon
              const isActive =
                item.path === '/' ? location.pathname === '/' : location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)
              return (
                <button
                  key={item.path}
                  onClick={() => {
                    navigate(item.path)
                    setSidebarOpen(false)
                  }}
                  className={`flex w-full items-center space-x-3 rounded-xl px-4 py-3 transition-all ${
                    isActive ? 'bg-white/20 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  <Icon className="h-5 w-5 flex-shrink-0" />
                  {!sidebarCollapsed && <span>{item.label}</span>}
                </button>
              )
            })}
          </nav>

          <div className="border-t border-white/10 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-indigo-500 to-violet-500">
                  {user?.phone?.slice(-2) || 'A'}
                </div>
                {!sidebarCollapsed && (
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{user?.phone || '管理员'}</p>
                    <p className="text-xs text-white/60">管理员</p>
                  </div>
                )}
              </div>
              {!sidebarCollapsed && (
                <button
                  onClick={() => void handleLogout()}
                  className="rounded-lg p-2 transition-colors hover:bg-white/10"
                  title="退出登录"
                >
                  <LogOut className="h-5 w-5" />
                </button>
              )}
            </div>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 lg:px-6">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-lg p-2 hover:bg-gray-100 lg:hidden"
            >
              <Menu className="h-6 w-6" />
            </button>
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="hidden rounded-lg p-2 hover:bg-gray-100 lg:flex"
            >
              {sidebarCollapsed ? <ChevronRight className="h-5 w-5" /> : <ChevronLeft className="h-5 w-5" />}
            </button>
            <h2 className="text-lg font-semibold text-gray-900">
              {menuItems.find((item) =>
                item.path === '/' ? location.pathname === '/' : location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)
              )?.label || '管理后台'}
            </h2>
          </div>
          <button
            onClick={() => void handleLogout()}
            className="hidden items-center space-x-2 rounded-lg px-4 py-2 text-gray-600 transition-colors hover:bg-gray-100 lg:flex"
          >
            <LogOut className="h-4 w-4" />
            <span>退出</span>
          </button>
        </header>

        <div className="flex-1 overflow-auto p-4 lg:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

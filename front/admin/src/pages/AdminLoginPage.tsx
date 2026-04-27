import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import { Lock, Phone, ArrowRight, Loader2, ShieldCheck } from 'lucide-react'
import { extractApiErrorMessage } from '../api'
import { useAdminAuthStore } from '../store'

export default function AdminLoginPage() {
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const login = useAdminAuthStore((state) => state.login)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!phone || !password) {
      toast.error('请输入管理员手机号和密码')
      return
    }

    setLoading(true)
    try {
      await login(phone, password)
      toast.success('登录成功')
      navigate('/')
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '登录失败，请检查账号权限'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-120px] top-[-130px] h-80 w-80 rounded-full bg-indigo-500/25 blur-3xl" />
        <div className="absolute -right-20 bottom-[-100px] h-80 w-80 rounded-full bg-fuchsia-500/15 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_25%,rgba(99,102,241,0.18),transparent_40%),radial-gradient(circle_at_80%_75%,rgba(168,85,247,0.16),transparent_44%)]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-md"
      >
        <div className="rounded-3xl border border-white/15 bg-white/95 p-8 shadow-2xl shadow-slate-950/30 backdrop-blur">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-700 shadow-lg shadow-indigo-500/30">
              <ShieldCheck className="h-7 w-7 text-white" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">管理后台登录</h1>
            <p className="mt-2 text-sm text-slate-500">仅限管理员账号访问数据看板、知识库与题库控制台。</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">管理员手机号</span>
              <div className="group relative">
                <Phone className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-indigo-500" />
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100"
                  placeholder="请输入管理员手机号"
                  autoComplete="tel"
                />
              </div>
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">密码</span>
              <div className="group relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-indigo-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100"
                  placeholder="请输入密码"
                  autoComplete="current-password"
                />
              </div>
            </label>

            <button
              type="submit"
              disabled={loading}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 text-sm font-medium text-white shadow-lg shadow-indigo-500/30 transition-all hover:-translate-y-0.5 hover:from-indigo-600 hover:to-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <>
                  <Loader2 className="h-[18px] w-[18px] animate-spin" />
                  登录中...
                </>
              ) : (
                <>
                  登录后台
                  <ArrowRight className="h-[18px] w-[18px]" />
                </>
              )}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}

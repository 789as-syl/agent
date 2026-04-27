import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import { Lock, Phone, User, ArrowRight, Loader2 } from 'lucide-react'
import { extractApiErrorMessage } from '../api'
import { useAuthStore } from '../store'

export default function RegisterPage() {
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const register = useAuthStore((state) => state.register)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!phone || !password || !confirmPassword) {
      toast.error('请填写所有字段')
      return
    }
    if (password !== confirmPassword) {
      toast.error('两次输入的密码不一致')
      return
    }
    if (password.length < 8) {
      toast.error('密码长度至少 8 位')
      return
    }
    if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
      toast.error('密码需包含大写字母、小写字母和数字')
      return
    }

    setLoading(true)
    try {
      await register(phone, password)
      toast.success('注册成功')
      navigate('/')
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '注册失败，请稍后重试'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-80px] top-[-140px] h-80 w-80 rounded-full bg-emerald-500/22 blur-3xl" />
        <div className="absolute -right-24 bottom-[-100px] h-80 w-80 rounded-full bg-indigo-500/26 blur-3xl" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(56,189,248,0.14),transparent_40%),radial-gradient(circle_at_30%_70%,rgba(16,185,129,0.12),transparent_45%)]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-md"
      >
        <div className="rounded-3xl border border-white/15 bg-white/95 p-8 shadow-2xl shadow-slate-950/25 backdrop-blur">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-indigo-600 shadow-lg shadow-emerald-500/30">
              <User className="h-7 w-7 text-white" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">创建账号</h1>
            <p className="mt-2 text-sm text-slate-500">完成注册后即可开始知识库问答与会话管理。</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">手机号</span>
              <div className="group relative">
                <Phone className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-emerald-500" />
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-emerald-300 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  placeholder="请输入手机号"
                  autoComplete="tel"
                />
              </div>
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">密码</span>
              <div className="group relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-emerald-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-emerald-300 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  placeholder="至少 6 位密码"
                  autoComplete="new-password"
                />
              </div>
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">确认密码</span>
              <div className="group relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-emerald-500" />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-emerald-300 focus:bg-white focus:ring-4 focus:ring-emerald-100"
                  placeholder="再次输入密码"
                  autoComplete="new-password"
                />
              </div>
            </label>

            <button
              type="submit"
              disabled={loading}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-indigo-600 text-sm font-medium text-white shadow-lg shadow-emerald-500/30 transition-all hover:-translate-y-0.5 hover:from-emerald-600 hover:to-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <>
                  <Loader2 className="h-[18px] w-[18px] animate-spin" />
                  注册中...
                </>
              ) : (
                <>
                  立即注册
                  <ArrowRight className="h-[18px] w-[18px]" />
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            已有账号？
            <Link to="/login" className="ml-1 font-medium text-indigo-600 transition-colors hover:text-indigo-700">
              去登录
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  )
}

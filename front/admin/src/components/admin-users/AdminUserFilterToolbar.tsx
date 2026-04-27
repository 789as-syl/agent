import { Search } from 'lucide-react'
import type { ReactNode } from 'react'
import type { AdminUserStatus } from '../../types'

interface AdminUserFilterToolbarProps {
  title: string
  description: string
  searchInput: string
  statusInput: AdminUserStatus | 'all'
  onSearchInputChange: (value: string) => void
  onStatusInputChange: (value: AdminUserStatus | 'all') => void
  onSubmit: () => void
  submitLabel?: string
  actions?: ReactNode
}

export function AdminUserFilterToolbar({
  title,
  description,
  searchInput,
  statusInput,
  onSearchInputChange,
  onStatusInputChange,
  onSubmit,
  submitLabel = '查询',
  actions,
}: AdminUserFilterToolbarProps) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        </div>
        {actions}
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_120px]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            value={searchInput}
            onChange={(event) => onSearchInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSubmit()
            }}
            placeholder="搜索用户 ID / 手机号"
            className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100"
          />
        </label>

        <select
          value={statusInput}
          onChange={(event) => onStatusInputChange(event.target.value as AdminUserStatus | 'all')}
          className="h-11 rounded-2xl border border-slate-200 bg-white px-3 text-sm text-slate-600 outline-none transition-all focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
        >
          <option value="all">全部状态</option>
          <option value="active">正常</option>
          <option value="disabled">已封禁</option>
        </select>

        <button
          onClick={onSubmit}
          className="inline-flex h-11 items-center justify-center rounded-2xl bg-slate-900 px-4 text-sm font-medium text-white transition-all hover:bg-slate-800"
        >
          {submitLabel}
        </button>
      </div>
    </section>
  )
}

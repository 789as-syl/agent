import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { AdminUserStatus } from '../../types'
import { getStatusBadgeClassName, statusLabelMap } from './adminUserMeta'

export function AdminUserStatusBadge({ status }: { status: AdminUserStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${getStatusBadgeClassName(status)}`}>
      {statusLabelMap[status]}
    </span>
  )
}

interface SummaryMetricCardProps {
  icon: LucideIcon
  label: string
  value: ReactNode
  hint: string
  tone?: 'indigo' | 'emerald' | 'amber' | 'slate'
}

const metricToneClassMap: Record<NonNullable<SummaryMetricCardProps['tone']>, string> = {
  indigo: 'bg-indigo-50 text-indigo-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  amber: 'bg-amber-50 text-amber-600',
  slate: 'bg-slate-100 text-slate-600',
}

export function SummaryMetricCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = 'slate',
}: SummaryMetricCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</div>
          <p className="mt-2 text-xs leading-5 text-slate-500">{hint}</p>
        </div>
        <div className={`flex h-11 w-11 items-center justify-center rounded-2xl ${metricToneClassMap[tone]}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  )
}

interface PanelEmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
}

export function PanelEmptyState({ icon: Icon, title, description }: PanelEmptyStateProps) {
  return (
    <div className="flex h-full min-h-[240px] flex-col items-center justify-center px-6 py-10 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
        <Icon className="h-7 w-7" />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-slate-700">{title}</h3>
      <p className="mt-2 max-w-xs text-xs leading-5 text-slate-500">{description}</p>
    </div>
  )
}

interface PaginationControlsProps {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
  summary: ReactNode
}

export function PaginationControls({
  page,
  totalPages,
  onPrev,
  onNext,
  summary,
}: PaginationControlsProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3">
      <div className="text-xs leading-5 text-slate-500">{summary}</div>
      <div className="flex items-center gap-2">
        <button
          onClick={onPrev}
          disabled={page <= 1}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          上一页
        </button>
        <span className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white">
          {page} / {totalPages}
        </span>
        <button
          onClick={onNext}
          disabled={page >= totalPages}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          下一页
        </button>
      </div>
    </div>
  )
}

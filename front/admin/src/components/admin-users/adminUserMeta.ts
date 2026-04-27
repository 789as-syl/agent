import type { AdminUserStatus } from '../../types'

export const USER_PAGE_SIZE = 20
export const CONVERSATION_PAGE_SIZE = 20
export const MESSAGE_PAGE_SIZE = 100

export const statusLabelMap: Record<AdminUserStatus, string> = {
  active: '正常',
  disabled: '已封禁',
}

export const roleLabelMap: Record<string, string> = {
  user: '用户',
  assistant: '助手',
  system: '系统',
}

export const traceStatusLabelMap: Record<string, string> = {
  pending: '待处理',
  running: '处理中',
  completed: '已完成',
  error: '异常',
}

export const formatDateTime = (value?: string | null) => {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN')
}

export const formatTraceTimestamp = (value?: number) => {
  if (!value) return '—'
  const normalized = value > 10_000_000_000 ? value : value * 1000
  return new Date(normalized).toLocaleString('zh-CN')
}

export const getStatusBadgeClassName = (status: AdminUserStatus) =>
  status === 'active'
    ? 'border border-emerald-100 bg-emerald-50 text-emerald-700'
    : 'border border-rose-100 bg-rose-50 text-rose-700'

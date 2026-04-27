import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  ArrowRight,
  Ban,
  Clock3,
  Loader2,
  MessageSquare,
  Phone,
  RotateCcw,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react'

import { extractApiErrorMessage } from '../api'
import { AdminUserFilterToolbar } from '../components/admin-users/AdminUserFilterToolbar'
import {
  AdminUserStatusBadge,
  PaginationControls,
  PanelEmptyState,
  SummaryMetricCard,
} from '../components/admin-users/AdminUserUi'
import {
  CONVERSATION_PAGE_SIZE,
  USER_PAGE_SIZE,
  formatDateTime,
} from '../components/admin-users/adminUserMeta'
import { useAdminUserManagementStore } from '../store'
import type { AdminUser, AdminUserStatus } from '../types'

export default function UserAccountManagementPage() {
  const navigate = useNavigate()
  const {
    users,
    total,
    loading,
    error,
    page,
    pageSize,
    query,
    statusFilter,
    selectedUser,
    fetchUsers,
    fetchUserDetail,
    updateUserStatus,
    selectUser,
    fetchConversations,
  } = useAdminUserManagementStore()

  const [searchInput, setSearchInput] = useState(query)
  const [statusInput, setStatusInput] = useState<AdminUserStatus | 'all'>(statusFilter)
  const [submitting, setSubmitting] = useState(false)
  const [actionModal, setActionModal] = useState<{ user: AdminUser; nextStatus: AdminUserStatus } | null>(null)
  const [banReason, setBanReason] = useState('')

  useEffect(() => {
    void fetchUsers({
      page: 1,
      pageSize: USER_PAGE_SIZE,
      q: query,
      status: statusFilter,
    })
  }, [fetchUsers, query, statusFilter])

  useEffect(() => {
    setSearchInput(query)
  }, [query])

  useEffect(() => {
    setStatusInput(statusFilter)
  }, [statusFilter])

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize || 1)), [pageSize, total])
  const disabledCount = useMemo(() => users.filter((item) => item.status === 'disabled').length, [users])

  const handleSearch = async (nextPage = 1) => {
    await fetchUsers({
      page: nextPage,
      pageSize: USER_PAGE_SIZE,
      q: searchInput.trim(),
      status: statusInput,
    })
  }

  const handleReviewSessions = (user: AdminUser) => {
    selectUser(user)
    void fetchUserDetail(user.id)
    void fetchConversations(user.id, { page: 1, pageSize: CONVERSATION_PAGE_SIZE })
    navigate('/user-sessions')
  }

  const handleSubmitStatusUpdate = async () => {
    if (!actionModal) return
    if (actionModal.nextStatus === 'disabled' && !banReason.trim()) {
      toast.error('请填写封禁业务原因')
      return
    }

    setSubmitting(true)
    try {
      await updateUserStatus(
        actionModal.user.id,
        actionModal.nextStatus,
        actionModal.nextStatus === 'disabled' ? banReason.trim() : null
      )
      toast.success(actionModal.nextStatus === 'disabled' ? '用户已封禁' : '用户已解封')
      await fetchUsers({
        page,
        pageSize: USER_PAGE_SIZE,
        q: searchInput.trim(),
        status: statusInput,
      })
      if (selectedUser?.id === actionModal.user.id) {
        await fetchUserDetail(actionModal.user.id)
      }
      setActionModal(null)
      setBanReason('')
    } catch (requestError) {
      toast.error(extractApiErrorMessage(requestError, '更新用户状态失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-900 p-6 text-white shadow-sm">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-medium text-indigo-100">
              <ShieldCheck className="h-3.5 w-3.5" />
              用户账号管理
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight">聚焦账号状态维护，不和会话审阅混在一起</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-200">
              本页只处理用户基础信息、状态筛选、封禁与解封。会话审阅被拆到独立页面，降低信息噪音，操作更聚焦。
            </p>
          </div>

          <button
            onClick={() => navigate('/user-sessions')}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/15"
          >
            前往会话审阅页
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <SummaryMetricCard
          icon={Users}
          label="当前筛选用户"
          value={users.length}
          hint={`筛选结果共 ${total} 条记录`}
          tone="indigo"
        />
        <SummaryMetricCard
          icon={Ban}
          label="当前页已封禁"
          value={disabledCount}
          hint="仅统计当前页，便于快速核对封禁密度"
          tone="amber"
        />
        <SummaryMetricCard
          icon={MessageSquare}
          label="当前审阅对象"
          value={<span className="truncate text-lg">{selectedUser?.phone ?? '未指定'}</span>}
          hint="点击“审阅会话”会跳转到独立审阅页"
          tone="emerald"
        />
      </div>

      <AdminUserFilterToolbar
        title="检索账号"
        description="支持按用户 ID / 手机号搜索，并按状态筛选。"
        searchInput={searchInput}
        statusInput={statusInput}
        onSearchInputChange={setSearchInput}
        onStatusInputChange={setStatusInput}
        onSubmit={() => void handleSearch(1)}
        actions={
          <div className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            <span>第 {page} 页</span>
            <span>·</span>
            <span>共 {totalPages} 页</span>
          </div>
        }
      />

      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">账号列表</h2>
            <p className="mt-1 text-sm text-slate-500">状态操作保留确认环节，封禁必须填写业务原因。</p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-2xl bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <span>总计 {total}</span>
            <span>·</span>
            <span>
              第 {page} / {totalPages} 页
            </span>
          </div>
        </div>

        {error && (
          <div className="border-b border-rose-100 bg-rose-50 px-5 py-3 text-sm text-rose-600">
            {error}
          </div>
        )}

        <div className="space-y-4 p-4">
          {loading ? (
            Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="rounded-3xl border border-slate-200 bg-white p-5">
                <div className="h-5 w-40 animate-pulse rounded bg-slate-100" />
                <div className="mt-4 grid gap-3 lg:grid-cols-3">
                  <div className="h-24 animate-pulse rounded-2xl bg-slate-100" />
                  <div className="h-24 animate-pulse rounded-2xl bg-slate-100" />
                  <div className="h-24 animate-pulse rounded-2xl bg-slate-100" />
                </div>
              </div>
            ))
          ) : users.length === 0 ? (
            <PanelEmptyState
              icon={Users}
              title="暂无匹配用户"
              description="请调整搜索条件或状态筛选后重试。"
            />
          ) : (
            users.map((user) => {
              const isSelected = selectedUser?.id === user.id

              return (
                <article
                  key={user.id}
                  className={`rounded-3xl border p-5 transition-all ${
                    isSelected
                      ? 'border-indigo-200 bg-indigo-50/40 shadow-sm'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
                  }`}
                >
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
                          <Phone className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-lg font-semibold text-slate-900">{user.phone}</h3>
                            <AdminUserStatusBadge status={user.status} />
                            {isSelected && (
                              <span className="rounded-full border border-indigo-200 bg-white px-2.5 py-1 text-xs font-medium text-indigo-600">
                                当前审阅对象
                              </span>
                            )}
                          </div>
                          <p className="mt-1 truncate font-mono text-xs text-slate-500">{user.id}</p>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 lg:grid-cols-3">
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">账号创建</p>
                          <div className="mt-2 flex items-center gap-2 text-sm font-medium text-slate-800">
                            <Clock3 className="h-4 w-4 text-slate-400" />
                            {formatDateTime(user.created_at)}
                          </div>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">状态变更</p>
                          <p className="mt-2 text-sm font-medium text-slate-800">
                            {formatDateTime(user.status_changed_at)}
                          </p>
                          <p className="mt-2 text-xs leading-5 text-slate-500">
                            {user.status === 'disabled'
                              ? '已进入封禁链路，登录与令牌刷新都会被拒绝。'
                              : '账号处于正常状态，可继续登录与访问。'}
                          </p>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">业务备注</p>
                          <p className="mt-2 text-sm leading-6 text-slate-700">
                            {user.ban_reason || '当前无封禁业务原因记录'}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="flex shrink-0 flex-col gap-2 xl:w-44">
                      <button
                        onClick={() => handleReviewSessions(user)}
                        className="inline-flex items-center justify-center gap-2 rounded-2xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-indigo-700"
                      >
                        <MessageSquare className="h-4 w-4" />
                        审阅会话
                      </button>

                      {user.status === 'active' ? (
                        <button
                          onClick={() => {
                            setActionModal({ user, nextStatus: 'disabled' })
                            setBanReason('')
                          }}
                          className="inline-flex items-center justify-center gap-2 rounded-2xl border border-rose-200 bg-white px-4 py-3 text-sm font-medium text-rose-600 transition-all hover:bg-rose-50"
                        >
                          <Ban className="h-4 w-4" />
                          封禁用户
                        </button>
                      ) : (
                        <button
                          onClick={() => {
                            setActionModal({ user, nextStatus: 'active' })
                            setBanReason('')
                          }}
                          className="inline-flex items-center justify-center gap-2 rounded-2xl border border-emerald-200 bg-white px-4 py-3 text-sm font-medium text-emerald-600 transition-all hover:bg-emerald-50"
                        >
                          <RotateCcw className="h-4 w-4" />
                          解封用户
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              )
            })
          )}
        </div>

        <PaginationControls
          page={page}
          totalPages={totalPages}
          onPrev={() => void handleSearch(Math.max(1, page - 1))}
          onNext={() => void handleSearch(Math.min(totalPages, page + 1))}
          summary="封禁与解封只变更状态；封禁原因会作为业务审计记录保留。"
        />
      </section>

      {actionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-[28px] bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-slate-900">
                  {actionModal.nextStatus === 'disabled' ? '确认封禁用户' : '确认解封用户'}
                </h3>
                <p className="mt-2 text-sm text-slate-500">手机号：{actionModal.user.phone}</p>
              </div>
              <button
                onClick={() => {
                  setActionModal(null)
                  setBanReason('')
                }}
                className="rounded-xl p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {actionModal.nextStatus === 'disabled' ? (
              <div className="mt-5 space-y-3">
                <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-700">
                  封禁后，该用户的登录、刷新令牌和受保护接口访问都会被拒绝，请确认业务原因准确可追溯。
                </div>
                <textarea
                  value={banReason}
                  onChange={(event) => setBanReason(event.target.value)}
                  rows={4}
                  placeholder="请输入业务原因（必填）"
                  className="w-full rounded-2xl border border-slate-200 p-3 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                />
              </div>
            ) : (
              <div className="mt-5 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-700">
                解封后，用户可重新登录并继续访问受保护接口。
              </div>
            )}

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => {
                  setActionModal(null)
                  setBanReason('')
                }}
                className="rounded-2xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600"
              >
                取消
              </button>
              <button
                onClick={() => void handleSubmitStatusUpdate()}
                disabled={submitting}
                className={`inline-flex items-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60 ${
                  actionModal.nextStatus === 'disabled' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                {actionModal.nextStatus === 'disabled' ? '确认封禁' : '确认解封'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

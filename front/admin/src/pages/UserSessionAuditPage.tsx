import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  ArrowRight,
  Clock3,
  Loader2,
  MessageSquare,
  MessagesSquare,
  ShieldCheck,
  Users,
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
  MESSAGE_PAGE_SIZE,
  USER_PAGE_SIZE,
  formatDateTime,
  roleLabelMap,
  formatTraceTimestamp,
  traceStatusLabelMap,
} from '../components/admin-users/adminUserMeta'
import { useAdminUserManagementStore } from '../store'
import type { AdminConversationSummary, AdminUser, AdminUserStatus } from '../types'

export default function UserSessionAuditPage() {
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
    userDetailLoading,
    conversations,
    conversationsTotal,
    conversationsLoading,
    conversationsPage,
    conversationsPageSize,
    selectedConversation,
    messages,
    messagesTotal,
    messagesLoading,
    messagesPage,
    messagesPageSize,
    fetchUsers,
    fetchUserDetail,
    selectUser,
    fetchConversations,
    selectConversation,
    fetchMessages,
    clearAuditState,
  } = useAdminUserManagementStore()

  const [searchInput, setSearchInput] = useState(query)
  const [statusInput, setStatusInput] = useState<AdminUserStatus | 'all'>(statusFilter)

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
  const conversationTotalPages = useMemo(
    () => Math.max(1, Math.ceil(conversationsTotal / conversationsPageSize || 1)),
    [conversationsPageSize, conversationsTotal]
  )
  const messageTotalPages = useMemo(
    () => Math.max(1, Math.ceil(messagesTotal / messagesPageSize || 1)),
    [messagesPageSize, messagesTotal]
  )

  const handleSearch = async (nextPage = 1) => {
    await fetchUsers({
      page: nextPage,
      pageSize: USER_PAGE_SIZE,
      q: searchInput.trim(),
      status: statusInput,
    })
  }

  const handleSelectUser = async (user: AdminUser) => {
    selectUser(user)
    try {
      await fetchUserDetail(user.id)
      await fetchConversations(user.id, { page: 1, pageSize: CONVERSATION_PAGE_SIZE })
    } catch (requestError) {
      toast.error(extractApiErrorMessage(requestError, '加载用户会话失败'))
    }
  }

  const handleSelectConversation = async (conversation: AdminConversationSummary) => {
    if (!selectedUser) return

    selectConversation(conversation)
    try {
      await fetchMessages(selectedUser.id, conversation.id, { page: 1, pageSize: MESSAGE_PAGE_SIZE })
    } catch (requestError) {
      toast.error(extractApiErrorMessage(requestError, '加载会话消息失败'))
    }
  }

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-gradient-to-br from-slate-900 via-indigo-900 to-cyan-900 p-6 text-white shadow-sm">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-medium text-cyan-100">
              <MessagesSquare className="h-3.5 w-3.5" />
              用户会话审阅
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight">独立审阅用户会话与消息详情</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-100/90">
              本页只做只读审计：先定位用户，再查看会话列表，最后按时间顺序审阅消息与脱敏后的内部过程。
            </p>
          </div>

          <button
            onClick={() => navigate('/users')}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/15"
          >
            返回账号管理
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <SummaryMetricCard
          icon={Users}
          label="用户检索结果"
          value={total}
          hint="左侧列表支持按用户 ID / 手机号定位审阅对象"
          tone="indigo"
        />
        <SummaryMetricCard
          icon={MessagesSquare}
          label="当前用户会话数"
          value={selectedUser ? conversationsTotal : '—'}
          hint={selectedUser ? `当前审阅用户：${selectedUser.phone}` : '请先选择一个用户'}
          tone="emerald"
        />
        <SummaryMetricCard
          icon={MessageSquare}
          label="当前会话消息数"
          value={selectedConversation ? messagesTotal : '—'}
          hint={selectedConversation ? selectedConversation.title : '请选择会话以查看消息详情'}
          tone="amber"
        />
      </div>

      <AdminUserFilterToolbar
        title="检索审阅对象"
        description="搜索用户后，在下方分栏中依次查看用户、会话与消息详情。"
        searchInput={searchInput}
        statusInput={statusInput}
        onSearchInputChange={setSearchInput}
        onStatusInputChange={setStatusInput}
        onSubmit={() => void handleSearch(1)}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {(selectedUser || selectedConversation) && (
              <button
                onClick={() => clearAuditState()}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs font-medium text-slate-600 transition-all hover:border-slate-300"
              >
                清空当前审阅
              </button>
            )}
            <div className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
              <span>第 {page} 页</span>
              <span>·</span>
              <span>共 {totalPages} 页</span>
            </div>
          </div>
        }
      />

      {error && (
        <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-600">
          {error}
        </div>
      )}

      <section className="grid gap-6 xl:grid-cols-[320px_360px_minmax(0,1fr)]">
        <div className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-4">
            <h2 className="text-lg font-semibold text-slate-900">用户列表</h2>
            <p className="mt-1 text-sm text-slate-500">选择用户后加载该用户的会话列表。</p>
          </div>

          <div className="space-y-3 p-4">
            {loading ? (
              Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="rounded-2xl border border-slate-200 p-4">
                  <div className="h-4 w-24 animate-pulse rounded bg-slate-100" />
                  <div className="mt-3 h-3 w-36 animate-pulse rounded bg-slate-100" />
                  <div className="mt-4 h-10 animate-pulse rounded-xl bg-slate-100" />
                </div>
              ))
            ) : users.length === 0 ? (
              <PanelEmptyState
                icon={Users}
                title="没有可审阅的用户"
                description="请先调整筛选条件，或返回账号管理页检查用户状态。"
              />
            ) : (
              users.map((user) => {
                const active = selectedUser?.id === user.id

                return (
                  <button
                    key={user.id}
                    onClick={() => void handleSelectUser(user)}
                    className={`w-full rounded-2xl border p-4 text-left transition-all ${
                      active
                        ? 'border-indigo-200 bg-indigo-50 shadow-sm'
                        : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">{user.phone}</p>
                        <p className="mt-1 truncate font-mono text-[11px] text-slate-500">{user.id}</p>
                      </div>
                      <AdminUserStatusBadge status={user.status} />
                    </div>
                    <div className="mt-4 rounded-xl bg-slate-50 px-3 py-2">
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Clock3 className="h-3.5 w-3.5" />
                        创建于 {formatDateTime(user.created_at)}
                      </div>
                    </div>
                  </button>
                )
              })
            )}
          </div>

          <PaginationControls
            page={page}
            totalPages={totalPages}
            onPrev={() => void handleSearch(Math.max(1, page - 1))}
            onNext={() => void handleSearch(Math.min(totalPages, page + 1))}
            summary={`共 ${total} 位用户`}
          />
        </div>

        <div className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">会话列表</h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selectedUser ? `当前用户：${selectedUser.phone}` : '请先在左侧选择用户'}
                </p>
              </div>
              {userDetailLoading && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
            </div>
          </div>

          {!selectedUser ? (
            <PanelEmptyState
              icon={MessagesSquare}
              title="等待选择用户"
              description="从左侧选中用户后，这里将展示该用户的只读会话列表。"
            />
          ) : conversationsLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="rounded-2xl border border-slate-200 p-4">
                  <div className="h-4 w-32 animate-pulse rounded bg-slate-100" />
                  <div className="mt-3 h-3 w-full animate-pulse rounded bg-slate-100" />
                </div>
              ))}
            </div>
          ) : conversations.length === 0 ? (
            <PanelEmptyState
              icon={MessagesSquare}
              title="暂无可读会话"
              description="该用户暂无可审阅的会话记录。"
            />
          ) : (
            <>
              <div className="space-y-3 p-4">
                {conversations.map((conversation) => {
                  const active = selectedConversation?.id === conversation.id

                  return (
                    <button
                      key={conversation.id}
                      onClick={() => void handleSelectConversation(conversation)}
                      className={`w-full rounded-2xl border p-4 text-left transition-all ${
                        active
                          ? 'border-cyan-200 bg-cyan-50 shadow-sm'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">{conversation.title}</p>
                          <p className="mt-1 truncate font-mono text-[11px] text-slate-500">{conversation.id}</p>
                        </div>
                        <span
                          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                            conversation.is_deleted
                              ? 'border border-slate-200 bg-slate-100 text-slate-600'
                              : 'border border-emerald-100 bg-emerald-50 text-emerald-700'
                          }`}
                        >
                          {conversation.is_deleted ? '已删除' : '正常'}
                        </span>
                      </div>
                      <p className="mt-4 text-xs text-slate-500">
                        更新时间：{formatDateTime(conversation.updated_at)}
                      </p>
                    </button>
                  )
                })}
              </div>

              <PaginationControls
                page={conversationsPage}
                totalPages={conversationTotalPages}
                onPrev={() =>
                  selectedUser &&
                  void fetchConversations(selectedUser.id, {
                    page: Math.max(1, conversationsPage - 1),
                    pageSize: CONVERSATION_PAGE_SIZE,
                  })
                }
                onNext={() =>
                  selectedUser &&
                  void fetchConversations(selectedUser.id, {
                    page: Math.min(conversationTotalPages, conversationsPage + 1),
                    pageSize: CONVERSATION_PAGE_SIZE,
                  })
                }
                summary={`共 ${conversationsTotal} 个会话`}
              />
            </>
          )}
        </div>

        <div className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">消息详情（只读）</h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selectedConversation ? selectedConversation.title : '请选择会话查看消息详情'}
                </p>
              </div>
              {messagesLoading && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
            </div>
          </div>

          {!selectedUser ? (
            <PanelEmptyState
              icon={MessageSquare}
              title="等待选择用户"
              description="先选择用户，再进入具体会话。"
            />
          ) : !selectedConversation ? (
            <PanelEmptyState
              icon={MessageSquare}
              title="等待选择会话"
              description="从中间栏选择一条会话后，这里会按时间顺序展示消息和脱敏内部过程。"
            />
          ) : messagesLoading ? (
            <div className="space-y-4 p-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="rounded-2xl border border-slate-200 p-4">
                  <div className="h-4 w-24 animate-pulse rounded bg-slate-100" />
                  <div className="mt-3 h-16 animate-pulse rounded-2xl bg-slate-100" />
                </div>
              ))}
            </div>
          ) : messages.length === 0 ? (
            <PanelEmptyState
              icon={MessageSquare}
              title="该会话暂无消息"
              description="当前会话没有可读的消息内容。"
            />
          ) : (
            <>
              <div className="max-h-[820px] space-y-4 overflow-y-auto p-4">
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`rounded-3xl border p-4 ${
                      message.role === 'user'
                        ? 'border-indigo-100 bg-indigo-50/50'
                        : message.role === 'assistant'
                          ? 'border-emerald-100 bg-emerald-50/50'
                          : 'border-slate-200 bg-slate-50'
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                            message.role === 'user'
                              ? 'bg-indigo-100 text-indigo-700'
                              : message.role === 'assistant'
                                ? 'bg-emerald-100 text-emerald-700'
                                : 'bg-slate-200 text-slate-700'
                          }`}
                        >
                          {roleLabelMap[message.role] || message.role}
                        </span>
                        <span className="text-xs text-slate-400">{formatDateTime(message.created_at)}</span>
                      </div>
                      <span className="font-mono text-[11px] text-slate-400">{message.id}</span>
                    </div>

                    <div className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">
                      {message.content}
                    </div>

                    {message.reply_to_message_id && (
                      <div className="mt-4 rounded-2xl border border-slate-200 bg-white/70 px-3 py-2 text-xs text-slate-500">
                        回复消息：{message.reply_to_message_id}
                      </div>
                    )}

                    {message.audit_playback && message.audit_playback.length > 0 && (
                      <div className="mt-4 rounded-3xl border border-slate-200 bg-white/80 p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                          <ShieldCheck className="h-4 w-4 text-indigo-500" />
                          审计回放（脱敏）
                        </div>
                        <p className="mt-2 text-xs leading-5 text-slate-500">
                          管理端只读展示脱敏后的执行片段，用于审计排查，不提供任何写操作。
                        </p>

                        <div className="mt-4 space-y-3">
                          {message.audit_playback.map((step) => (
                            <div key={step.id} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                  <h3 className="text-sm font-semibold text-slate-800">{step.title}</h3>
                                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                                    <span className="rounded-full bg-white px-2.5 py-1 text-slate-600">{step.kind}</span>
                                    <span>{traceStatusLabelMap[step.status] || step.status}</span>
                                    <span>{formatTraceTimestamp(step.timestamp)}</span>
                                  </div>
                                </div>
                              </div>
                              <div className="mt-3 whitespace-pre-wrap text-xs leading-6 text-slate-600">
                                {step.detail_sanitized || '无可展示内容'}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </article>
                ))}
              </div>

              <PaginationControls
                page={messagesPage}
                totalPages={messageTotalPages}
                onPrev={() =>
                  selectedUser &&
                  selectedConversation &&
                  void fetchMessages(selectedUser.id, selectedConversation.id, {
                    page: Math.max(1, messagesPage - 1),
                    pageSize: MESSAGE_PAGE_SIZE,
                  })
                }
                onNext={() =>
                  selectedUser &&
                  selectedConversation &&
                  void fetchMessages(selectedUser.id, selectedConversation.id, {
                    page: Math.min(messageTotalPages, messagesPage + 1),
                    pageSize: MESSAGE_PAGE_SIZE,
                  })
                }
                summary={`共 ${messagesTotal} 条消息`}
              />
            </>
          )}
        </div>
      </section>
    </div>
  )
}

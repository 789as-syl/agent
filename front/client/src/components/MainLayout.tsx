import { useMemo, useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MessageSquare,
  Plus,
  LogOut,
  Menu,
  X,
  History,
  Trash2,
  Edit3,
  Bot,
  CalendarDays,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { toast } from 'sonner'
import { useAuthStore, useConversationStore } from '../store'
import type { Conversation } from '../types'

const GROUP_ORDER = ['今天', '近 7 天', '更早'] as const

function getConversationGroup(createdAt: string) {
  const created = new Date(createdAt)
  const now = new Date()
  const diffMs = now.getTime() - created.getTime()
  const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000))

  if (diffDays <= 0) return '今天'
  if (diffDays <= 7) return '近 7 天'
  return '更早'
}

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [isEditing, setIsEditing] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const navigate = useNavigate()
  const location = useLocation()

  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const conversations = useConversationStore((state) => state.conversations)
  const currentConversation = useConversationStore((state) => state.currentConversation)
  const setCurrentConversation = useConversationStore((state) => state.setCurrentConversation)
  const fetchConversations = useConversationStore((state) => state.fetchConversations)
  const createConversation = useConversationStore((state) => state.createConversation)
  const updateConversation = useConversationStore((state) => state.updateConversation)
  const deleteConversation = useConversationStore((state) => state.deleteConversation)
  const loading = useConversationStore((state) => state.loading)

  useEffect(() => {
    if (!isAuthenticated) return
    fetchConversations()
  }, [isAuthenticated, fetchConversations])

  useEffect(() => {
    const conversationId = location.pathname.split('/')[1]
    if (!conversationId || conversationId === '') {
      setCurrentConversation(null)
      return
    }

    const conversation = conversations.find((c) => c.id === conversationId)
    if (conversation) {
      setCurrentConversation(conversation)
    }
  }, [location.pathname, conversations, setCurrentConversation])

  const groupedConversations = useMemo(() => {
    const groups: Record<string, Conversation[]> = {
      今天: [],
      '近 7 天': [],
      更早: [],
    }

    conversations.forEach((conversation) => {
      groups[getConversationGroup(conversation.created_at)].push(conversation)
    })

    return groups
  }, [conversations])

  const handleNewConversation = async () => {
    try {
      const conversation = await createConversation('新对话')
      navigate(`/${conversation.id}`)
      setSidebarOpen(false)
      toast.success('已创建新对话')
    } catch {
      toast.error('创建会话失败')
    }
  }

  const handleSelectConversation = (conversation: Conversation) => {
    setCurrentConversation(conversation)
    navigate(`/${conversation.id}`)
    setSidebarOpen(false)
  }

  const handleStartEdit = (conversation: Conversation, e: React.MouseEvent) => {
    e.stopPropagation()
    setIsEditing(conversation.id)
    setEditTitle(conversation.title)
  }

  const handleSaveEdit = async (id: string) => {
    if (!editTitle.trim()) {
      setIsEditing(null)
      return
    }

    try {
      await updateConversation(id, editTitle.trim())
      toast.success('会话名称已更新')
    } catch {
      toast.error('更新会话名称失败')
    } finally {
      setIsEditing(null)
    }
  }

  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('确定要删除这个会话吗？')) return

    try {
      await deleteConversation(id)
      if (currentConversation?.id === id) {
        navigate('/')
      }
      toast.success('会话已删除')
    } catch {
      toast.error('删除会话失败')
    }
  }

  const handleLogout = async () => {
    try {
      await logout()
      navigate('/login')
      toast.success('已退出登录')
    } catch {
      toast.error('退出登录失败')
    }
  }

  return (
    <div className="flex h-screen bg-slate-100 text-slate-900">
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-[2px] lg:hidden"
          />
        )}
      </AnimatePresence>

      <aside
        className={
          'fixed inset-y-0 left-0 z-50 flex w-80 flex-col border-r border-slate-200 bg-white shadow-2xl shadow-slate-950/5 transition-all lg:static lg:translate-x-0 ' +
          (sidebarCollapsed ? 'lg:w-20 ' : 'lg:w-80 ') +
          (sidebarOpen ? 'translate-x-0' : '-translate-x-full')
        }
      >
        <div className="border-b border-slate-200/80 px-4 pb-4 pt-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 shadow-lg shadow-indigo-500/30">
                <Bot className="h-5 w-5 text-white" />
              </div>
              {!sidebarCollapsed && (
                <div>
                <p className="text-base font-semibold leading-none">知识库问答</p>
                <p className="mt-1 text-xs text-slate-500">Conversation Workspace</p>
                </div>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setSidebarCollapsed((prev) => !prev)}
                className="hidden rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:inline-flex"
                title={sidebarCollapsed ? '展开导航栏' : '收起导航栏'}
              >
                {sidebarCollapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
              </button>
              <button
                onClick={() => setSidebarOpen(false)}
                className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:hidden"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          <button
            onClick={handleNewConversation}
            className={`flex h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 text-sm font-medium text-white shadow-lg shadow-indigo-500/30 transition-all hover:-translate-y-0.5 hover:from-indigo-600 hover:to-indigo-700 ${
              sidebarCollapsed ? 'w-11' : 'w-full'
            }`}
            title="新建对话"
          >
            <Plus className="h-4 w-4" />
            {!sidebarCollapsed && '新建对话'}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">
          {loading ? (
            <div className="space-y-2 px-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-xl bg-slate-100" />
              ))}
            </div>
          ) : conversations.length === 0 ? (
            <div className="mx-2 mt-14 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
              <History className="mx-auto mb-3 h-10 w-10 text-slate-300" />
              <p className="text-sm font-medium text-slate-500">暂无匹配会话</p>
              <p className="mt-1 text-xs text-slate-400">点击“新建对话”开始提问</p>
            </div>
          ) : (
            <div className="space-y-4">
              {GROUP_ORDER.map((group) => {
                const list = groupedConversations[group]
                if (!list || list.length === 0) return null

                return (
                  <section key={group} className="space-y-2 px-1">
                    {!sidebarCollapsed && (
                      <div className="flex items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        <CalendarDays className="h-3.5 w-3.5" />
                        {group}
                      </div>
                    )}
                    <div className="space-y-1.5">
                      {list.map((conversation) => {
                        const active = currentConversation?.id === conversation.id
                        return (
                          <motion.div
                            key={conversation.id}
                            whileHover={{ x: 2 }}
                            onClick={() => handleSelectConversation(conversation)}
                            className={`group cursor-pointer rounded-xl border px-3 py-2.5 transition-all ${
                              active
                                ? 'border-indigo-200 bg-indigo-50/80 shadow-sm'
                                : 'border-transparent hover:border-slate-200 hover:bg-slate-50'
                            }`}
                          >
                            {isEditing === conversation.id ? (
                              <input
                                autoFocus
                                value={editTitle}
                                onChange={(e) => setEditTitle(e.target.value)}
                                onBlur={() => void handleSaveEdit(conversation.id)}
                                onKeyDown={(e) => e.key === 'Enter' && void handleSaveEdit(conversation.id)}
                                onClick={(e) => e.stopPropagation()}
                                className="h-8 w-full rounded-lg border border-indigo-300 px-2 text-sm outline-none ring-2 ring-indigo-100"
                              />
                            ) : (
                              <>
                                <div className="flex items-start justify-between gap-2">
                                <div className="flex min-w-0 flex-1 items-center gap-2">
                                  <MessageSquare className={`mt-0.5 h-4 w-4 flex-shrink-0 ${active ? 'text-indigo-500' : 'text-slate-400'}`} />
                                  {!sidebarCollapsed && (
                                    <span className={`truncate text-sm ${active ? 'font-medium text-indigo-700' : 'text-slate-700'}`}>
                                        {conversation.title}
                                      </span>
                                  )}
                                </div>
                                  {!sidebarCollapsed && (
                                    <div className="hidden items-center gap-1 opacity-0 transition-opacity group-hover:flex group-hover:opacity-100">
                                    <button
                                      onClick={(e) => handleStartEdit(conversation, e)}
                                      className="rounded-md p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
                                      aria-label="编辑会话"
                                    >
                                      <Edit3 className="h-3.5 w-3.5" />
                                    </button>
                                    <button
                                      onClick={(e) => void handleDeleteConversation(conversation.id, e)}
                                      className="rounded-md p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                                      aria-label="删除会话"
                                    >
                                      <Trash2 className="h-3.5 w-3.5" />
                                    </button>
                                  </div>
                                  )}
                                </div>
                                {!sidebarCollapsed && (
                                  <p className="mt-1.5 text-[11px] text-slate-400">
                                    {new Date(conversation.created_at).toLocaleDateString()}
                                  </p>
                                )}
                              </>
                            )}
                          </motion.div>
                        )
                      })}
                    </div>
                  </section>
                )
              })}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200/80 p-4">
          <div className="flex items-center justify-between gap-2 rounded-2xl bg-slate-100/80 px-3 py-2">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-sm font-semibold text-white">
                {user?.phone?.slice(-2) || 'U'}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-800">{user?.phone || '用户'}</p>
                <p className="text-xs text-slate-500">标准权限</p>
              </div>
            </div>
            <button
              onClick={() => void handleLogout()}
              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-white hover:text-slate-700"
              title="退出登录"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur md:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h2 className="truncate text-base font-semibold text-slate-900 md:text-lg">
              {currentConversation?.title || '新对话'}
            </h2>
          </div>
        </header>

        <div className="flex-1 overflow-hidden">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

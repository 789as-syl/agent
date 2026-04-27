import { create } from 'zustand'
import type {
  AdminConversationAuditMessage,
  AdminConversationSummary,
  AdminUser,
  AdminUserStatus,
  IngestionJobResponse,
  KnowledgePointDeleteResponse,
  KnowledgePointResponse,
  QuestionImportResponse,
  QuestionBankResponse,
  QuestionResponse,
  VectorizationJobResponse,
} from '../types'
import { apiClient, authApi } from '../api'
import * as adminIngestionApi from '../api/admin-ingestion'
import * as adminQuestionsApi from '../api/admin-questions'
import * as adminUsersApi from '../api/admin-users'

interface AuthUser {
  id: string
  phone: string
  role: 'user' | 'admin'
}

interface AuthState {
  user: AuthUser | null
  isAuthenticated: boolean
  setUser: (user: AuthUser) => void
  login: (phone: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
}

interface KnowledgeQuery {
  page?: number
  pageSize?: number
  q?: string
  includeChunks?: boolean
}

interface KnowledgeState {
  knowledgePoints: KnowledgePointResponse[]
  total: number
  loading: boolean
  error: string | null
  page: number
  pageSize: number
  query: string
  fetchKnowledgePoints: (params?: KnowledgeQuery) => Promise<void>
  reindexKnowledgePoint: (id: string) => Promise<IngestionJobResponse>
  deleteKnowledgePoint: (id: string) => Promise<KnowledgePointDeleteResponse>
}

interface QuestionQuery {
  page?: number
  pageSize?: number
  q?: string
  bankId?: string
  questionType?: string
  isDirty?: boolean
}

interface QuestionState {
  questions: QuestionResponse[]
  questionBanks: QuestionBankResponse[]
  total: number
  loading: boolean
  error: string | null
  page: number
  pageSize: number
  query: string
  selectedBankId: string
  selectedType: string
  selectedDirty: 'all' | 'dirty' | 'clean'
  fetchQuestions: (params?: QuestionQuery) => Promise<void>
  fetchQuestionBanks: () => Promise<void>
  deleteQuestion: (id: string) => Promise<void>
  importQuestions: (data: FormData) => Promise<QuestionImportResponse>
  vectorizeQuestions: (data?: { only_dirty?: boolean; batch_size?: number }) => Promise<VectorizationJobResponse>
}

interface AdminUserQueryState {
  page?: number
  pageSize?: number
  q?: string
  status?: AdminUserStatus | 'all'
}

interface AdminUserConversationQueryState {
  page?: number
  pageSize?: number
}

interface AdminUserMessageQueryState {
  page?: number
  pageSize?: number
}

interface AdminUserManagementState {
  users: AdminUser[]
  total: number
  loading: boolean
  error: string | null
  page: number
  pageSize: number
  query: string
  statusFilter: AdminUserStatus | 'all'
  selectedUser: AdminUser | null
  userDetailLoading: boolean
  conversations: AdminConversationSummary[]
  conversationsTotal: number
  conversationsLoading: boolean
  conversationsPage: number
  conversationsPageSize: number
  selectedConversation: AdminConversationSummary | null
  messages: AdminConversationAuditMessage[]
  messagesTotal: number
  messagesLoading: boolean
  messagesPage: number
  messagesPageSize: number
  fetchUsers: (params?: AdminUserQueryState) => Promise<void>
  fetchUserDetail: (userId: string) => Promise<AdminUser | null>
  updateUserStatus: (userId: string, status: AdminUserStatus, banReason?: string | null) => Promise<AdminUser>
  selectUser: (user: AdminUser | null) => void
  fetchConversations: (userId: string, params?: AdminUserConversationQueryState) => Promise<void>
  selectConversation: (conversation: AdminConversationSummary | null) => void
  fetchMessages: (userId: string, conversationId: string, params?: AdminUserMessageQueryState) => Promise<void>
  clearAuditState: () => void
}

interface GlobalState {
  sidebarCollapsed: boolean
  setSidebarCollapsed: (collapsed: boolean) => void
}

export const useAdminAuthStore = create<AuthState>()((set, get) => {
  apiClient.setAuthFailureHandler(() => {
    set({ user: null, isAuthenticated: false })
  })

  return {
    user: null,
    isAuthenticated: false,

    setUser: (user: AuthUser) => {
      set({ user, isAuthenticated: true })
    },

    login: async (phone: string, password: string) => {
      await authApi.login({ phone, password })
      await get().fetchMe()

      const currentUser = get().user
      if (!currentUser || currentUser.role !== 'admin') {
        await get().logout()
        throw new Error('Admin role required')
      }
    },

    logout: async () => {
      try {
        await authApi.logout()
      } catch {
        // ignore logout error to keep local state clean
      }
      set({ user: null, isAuthenticated: false })
    },

    fetchMe: async () => {
      try {
        const user = await authApi.getMe()
        set({ user: { id: user.id, phone: user.phone, role: user.role } as AuthUser, isAuthenticated: true })
      } catch {
        set({ user: null, isAuthenticated: false })
        throw new Error('Session expired')
      }
    },
  }
})

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  knowledgePoints: [],
  total: 0,
  loading: false,
  error: null,
  page: 1,
  pageSize: 20,
  query: '',

  fetchKnowledgePoints: async (params = {}) => {
    const page = params.page ?? get().page
    const pageSize = params.pageSize ?? get().pageSize
    const q = params.q ?? get().query

    set({ loading: true, error: null })
    try {
      const response = await adminIngestionApi.getKnowledgePoints({
        page,
        page_size: pageSize,
        q,
        include_chunks: params.includeChunks ?? false,
      })
      set({
        knowledgePoints: response.items,
        total: response.total,
        page,
        pageSize,
        query: q,
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch knowledge points' })
    } finally {
      set({ loading: false })
    }
  },

  reindexKnowledgePoint: async (id: string) => {
    return adminIngestionApi.reindexKnowledgePoint(id)
  },

  deleteKnowledgePoint: async (id: string) => {
    return adminIngestionApi.deleteKnowledgePoint(id)
  },
}))

export const useQuestionStore = create<QuestionState>((set, get) => ({
  questions: [],
  questionBanks: [],
  total: 0,
  loading: false,
  error: null,
  page: 1,
  pageSize: 20,
  query: '',
  selectedBankId: '',
  selectedType: 'all',
  selectedDirty: 'all',

  fetchQuestionBanks: async () => {
    const response = await adminQuestionsApi.getQuestionBanks()
    set({ questionBanks: response.items })
  },

  fetchQuestions: async (params = {}) => {
    const page = params.page ?? get().page
    const pageSize = params.pageSize ?? get().pageSize
    const q = params.q ?? get().query
    const bankId = params.bankId ?? get().selectedBankId
    const questionType = params.questionType ?? get().selectedType
    const isDirtyFilter = params.isDirty ?? (get().selectedDirty === 'all' ? undefined : get().selectedDirty === 'dirty')

    set({ loading: true, error: null })
    try {
      const response = await adminQuestionsApi.getQuestions({
        page,
        page_size: pageSize,
        bank_id: bankId || undefined,
        q: q || undefined,
        question_type: questionType === 'all' ? undefined : questionType,
        is_dirty: isDirtyFilter,
      })

      set({
        questions: response.items,
        total: response.total,
        page,
        pageSize,
        query: q,
        selectedBankId: bankId,
        selectedType: questionType,
        selectedDirty: isDirtyFilter === undefined ? 'all' : isDirtyFilter ? 'dirty' : 'clean',
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch questions' })
    } finally {
      set({ loading: false })
    }
  },

  deleteQuestion: async (id: string) => {
    await adminQuestionsApi.deleteQuestion(id)
    await get().fetchQuestions({ page: get().page })
  },

  importQuestions: async (data: FormData) => {
    return adminQuestionsApi.importQuestions(data)
  },

  vectorizeQuestions: async (data = { only_dirty: true, batch_size: 10 }) => {
    return adminQuestionsApi.vectorizeQuestions(data)
  },
}))

export const useAdminUserManagementStore = create<AdminUserManagementState>((set, get) => ({
  users: [],
  total: 0,
  loading: false,
  error: null,
  page: 1,
  pageSize: 20,
  query: '',
  statusFilter: 'all',
  selectedUser: null,
  userDetailLoading: false,
  conversations: [],
  conversationsTotal: 0,
  conversationsLoading: false,
  conversationsPage: 1,
  conversationsPageSize: 20,
  selectedConversation: null,
  messages: [],
  messagesTotal: 0,
  messagesLoading: false,
  messagesPage: 1,
  messagesPageSize: 100,

  fetchUsers: async (params = {}) => {
    const page = params.page ?? get().page
    const pageSize = params.pageSize ?? get().pageSize
    const q = params.q ?? get().query
    const status = params.status ?? get().statusFilter

    set({ loading: true, error: null })
    try {
      const response = await adminUsersApi.getUsers({
        page,
        page_size: pageSize,
        q: q || undefined,
        status: status === 'all' ? undefined : status,
      })

      set({
        users: response.items,
        total: response.total,
        page,
        pageSize,
        query: q,
        statusFilter: status,
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch users' })
    } finally {
      set({ loading: false })
    }
  },

  fetchUserDetail: async (userId: string) => {
    set({ userDetailLoading: true, error: null })
    try {
      const user = await adminUsersApi.getUser(userId)
      set({ selectedUser: user })
      return user
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch user detail' })
      return null
    } finally {
      set({ userDetailLoading: false })
    }
  },

  updateUserStatus: async (userId: string, status: AdminUserStatus, banReason?: string | null) => {
    const updatedUser = await adminUsersApi.updateUserStatus(userId, {
      status,
      ban_reason: status === 'disabled' ? banReason ?? null : undefined,
    })

    set((state) => ({
      users: state.users.map((item) => (item.id === updatedUser.id ? updatedUser : item)),
      selectedUser: state.selectedUser?.id === updatedUser.id ? updatedUser : state.selectedUser,
    }))

    return updatedUser
  },

  selectUser: (user) =>
    set({
      selectedUser: user,
      selectedConversation: null,
      conversations: [],
      conversationsTotal: 0,
      conversationsPage: 1,
      messages: [],
      messagesTotal: 0,
      messagesPage: 1,
    }),

  fetchConversations: async (userId: string, params = {}) => {
    const page = params.page ?? get().conversationsPage
    const pageSize = params.pageSize ?? get().conversationsPageSize

    set({ conversationsLoading: true, error: null })
    try {
      const response = await adminUsersApi.listUserConversations(userId, {
        page,
        page_size: pageSize,
      })
      set({
        conversations: response.items,
        conversationsTotal: response.total,
        conversationsPage: page,
        conversationsPageSize: pageSize,
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch conversations' })
    } finally {
      set({ conversationsLoading: false })
    }
  },

  selectConversation: (conversation) =>
    set({
      selectedConversation: conversation,
      messages: [],
      messagesTotal: 0,
      messagesPage: 1,
    }),

  fetchMessages: async (userId: string, conversationId: string, params = {}) => {
    const page = params.page ?? get().messagesPage
    const pageSize = params.pageSize ?? get().messagesPageSize

    set({ messagesLoading: true, error: null })
    try {
      const response = await adminUsersApi.listConversationMessages(userId, conversationId, {
        page,
        page_size: pageSize,
      })
      set({
        messages: response.items,
        messagesTotal: response.total,
        messagesPage: page,
        messagesPageSize: pageSize,
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch conversation messages' })
    } finally {
      set({ messagesLoading: false })
    }
  },

  clearAuditState: () =>
    set({
      selectedUser: null,
      selectedConversation: null,
      conversations: [],
      conversationsTotal: 0,
      conversationsPage: 1,
      messages: [],
      messagesTotal: 0,
      messagesPage: 1,
    }),
}))

export const useAdminGlobalStore = create<GlobalState>((set) => ({
  sidebarCollapsed: false,
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
}))

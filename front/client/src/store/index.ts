import { create } from 'zustand'
import type { User, Conversation, Message } from '../types'
import { apiClient, authApi, conversationsApi } from '../api'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  setUser: (user: User) => void
  login: (phone: string, password: string) => Promise<void>
  register: (phone: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
}

interface ConversationState {
  conversations: Conversation[]
  currentConversation: Conversation | null
  messages: Message[]
  activeMessagesConversationId: string | null
  loading: boolean
  error: string | null
  setCurrentConversation: (conversation: Conversation | null) => void
  fetchConversations: () => Promise<void>
  createConversation: (title: string) => Promise<Conversation>
  updateConversation: (id: string, title: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  fetchMessages: (conversationId: string) => Promise<void>
  addMessage: (message: Message) => void
}

interface ChatState {
  currentRunId: string | null
  isRunning: boolean
  setCurrentRunId: (id: string | null) => void
  setIsRunning: (running: boolean) => void
  clearChat: () => void
}

interface GlobalState {
  loading: boolean
  error: string | null
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
}

export const useAuthStore = create<AuthState>()((set, get) => {
  apiClient.setAuthFailureHandler(() => {
    set({ user: null, isAuthenticated: false })
  })

  return {
    user: null,
    isAuthenticated: false,

    setUser: (user: User) => {
      set({ user, isAuthenticated: true })
    },

    login: async (phone: string, password: string) => {
      await authApi.login({ phone, password })
      await get().fetchMe()
    },

    register: async (phone: string, password: string) => {
      await authApi.register({ phone, password })
      await get().fetchMe()
    },

    logout: async () => {
      try {
        await authApi.logout()
      } catch {
        // ignore logout network failure; local session must still be cleared
      }
      set({ user: null, isAuthenticated: false })
    },

    fetchMe: async () => {
      try {
        const user = await authApi.getMe()
        set({ user, isAuthenticated: true })
      } catch {
        set({ user: null, isAuthenticated: false })
        throw new Error('Session expired')
      }
    },
  }
})

export const useConversationStore = create<ConversationState>((set) => ({
  conversations: [],
  currentConversation: null,
  messages: [],
  activeMessagesConversationId: null,
  loading: false,
  error: null,
  
  setCurrentConversation: (conversation) => set({ currentConversation: conversation }),
  
  fetchConversations: async () => {
    set({ loading: true, error: null })
    try {
      const response = await conversationsApi.list()
      set({ conversations: response.items })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to fetch conversations' })
    } finally {
      set({ loading: false })
    }
  },
  
  createConversation: async (title: string) => {
    const conversation = await conversationsApi.create({ title })
    set((state) => ({ conversations: [conversation, ...state.conversations] }))
    return conversation
  },
  
  updateConversation: async (id: string, title: string) => {
    const updated = await conversationsApi.update(id, { title })
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? updated : c)),
      currentConversation: state.currentConversation?.id === id ? updated : state.currentConversation,
    }))
  },
  
  deleteConversation: async (id: string) => {
    await conversationsApi.delete(id)
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      currentConversation: state.currentConversation?.id === id ? null : state.currentConversation,
    }))
  },
  
  fetchMessages: async (conversationId: string) => {
    set({ loading: true, error: null, activeMessagesConversationId: conversationId })
    try {
      const response = await conversationsApi.listMessages(conversationId)
      set((state) => {
        if (state.activeMessagesConversationId !== conversationId) {
          return { loading: false }
        }
        const pendingMessages = state.messages.filter((message) => (
          message.conversation_id === conversationId
          && message.id.startsWith('pending-user-')
          && !response.items.some((item) => (
            item.id === message.id
            || (
              item.role === message.role
              && item.role === 'user'
              && item.content.trim() === message.content.trim()
            )
          ))
        ))
        return { messages: [...response.items, ...pendingMessages], loading: false }
      })
    } catch (error) {
      set((state) => {
        if (state.activeMessagesConversationId !== conversationId) {
          return { loading: false }
        }
        return {
          error: error instanceof Error ? error.message : 'Failed to fetch messages',
          loading: false,
        }
      })
      throw error
    }
  },
  
  addMessage: (message: Message) => {
    set((state) => {
      const messages = state.activeMessagesConversationId === message.conversation_id
        ? state.messages.filter((item) => item.conversation_id === message.conversation_id)
        : []
      const existingIndex = messages.findIndex((item) => item.id === message.id)
      const nextMessages = existingIndex >= 0
        ? messages.map((item, index) => (index === existingIndex ? message : item))
        : [...messages, message]
      return {
        activeMessagesConversationId: message.conversation_id,
        messages: nextMessages,
      }
    })
  },
}))

export const useChatStore = create<ChatState>((set) => ({
  currentRunId: null,
  isRunning: false,
  
  setCurrentRunId: (id) => set({ currentRunId: id }),
  setIsRunning: (running) => set({ isRunning: running }),
  
  clearChat: () => {
    set({ currentRunId: null, isRunning: false })
  },
}))

export const useGlobalStore = create<GlobalState>((set) => ({
  loading: false,
  error: null,
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}))

"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.useGlobalStore = exports.useChatStore = exports.useConversationStore = exports.useAuthStore = void 0;
const zustand_1 = require("zustand");
const middleware_1 = require("zustand/middleware");
const api_1 = require("../api");
exports.useAuthStore = (0, zustand_1.create)()((0, middleware_1.persist)((set, get) => {
    api_1.apiClient.setAuthFailureHandler(() => {
        api_1.apiClient.clearToken();
        set({ accessToken: null, user: null, isAuthenticated: false });
    });
    return {
        accessToken: null,
        user: null,
        isAuthenticated: false,
        setAccessToken: (token) => {
            api_1.apiClient.setToken(token);
            set({ accessToken: token, isAuthenticated: true });
        },
        setUser: (user) => {
            set({ user });
        },
        login: async (phone, password) => {
            const response = await api_1.authApi.login({ phone, password });
            get().setAccessToken(response.access_token);
            await get().fetchMe();
        },
        register: async (phone, password) => {
            const response = await api_1.authApi.register({ phone, password });
            get().setAccessToken(response.access_token);
            await get().fetchMe();
        },
        logout: async () => {
            try {
                await api_1.authApi.logout();
            }
            catch {
                // ignore logout network failure; local session must still be cleared
            }
            api_1.apiClient.clearToken();
            set({ accessToken: null, user: null, isAuthenticated: false });
        },
        fetchMe: async () => {
            try {
                const user = await api_1.authApi.getMe();
                set({ user });
            }
            catch {
                await get().logout();
                throw new Error('Session expired');
            }
        },
    };
}, {
    name: 'auth-storage',
    partialize: (state) => ({ accessToken: state.accessToken, user: state.user, isAuthenticated: state.isAuthenticated }),
    onRehydrateStorage: () => (state) => {
        if (state?.accessToken) {
            api_1.apiClient.setToken(state.accessToken);
        }
    },
}));
exports.useConversationStore = (0, zustand_1.create)((set) => ({
    conversations: [],
    currentConversation: null,
    messages: [],
    loading: false,
    error: null,
    setCurrentConversation: (conversation) => set({ currentConversation: conversation }),
    fetchConversations: async () => {
        set({ loading: true, error: null });
        try {
            const response = await api_1.conversationsApi.list();
            set({ conversations: response.items });
        }
        catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to fetch conversations' });
        }
        finally {
            set({ loading: false });
        }
    },
    createConversation: async (title) => {
        const conversation = await api_1.conversationsApi.create({ title });
        set((state) => ({ conversations: [conversation, ...state.conversations] }));
        return conversation;
    },
    updateConversation: async (id, title) => {
        const updated = await api_1.conversationsApi.update(id, { title });
        set((state) => ({
            conversations: state.conversations.map((c) => (c.id === id ? updated : c)),
            currentConversation: state.currentConversation?.id === id ? updated : state.currentConversation,
        }));
    },
    deleteConversation: async (id) => {
        await api_1.conversationsApi.delete(id);
        set((state) => ({
            conversations: state.conversations.filter((c) => c.id !== id),
            currentConversation: state.currentConversation?.id === id ? null : state.currentConversation,
        }));
    },
    fetchMessages: async (conversationId) => {
        set({ loading: true, error: null });
        try {
            const response = await api_1.conversationsApi.listMessages(conversationId);
            set({ messages: response.items });
        }
        catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to fetch messages' });
        }
        finally {
            set({ loading: false });
        }
    },
    addMessage: (message) => {
        set((state) => ({ messages: [...state.messages, message] }));
    },
}));
exports.useChatStore = (0, zustand_1.create)((set) => ({
    currentRunId: null,
    isRunning: false,
    setCurrentRunId: (id) => set({ currentRunId: id }),
    setIsRunning: (running) => set({ isRunning: running }),
    clearChat: () => {
        set({ currentRunId: null, isRunning: false });
    },
}));
exports.useGlobalStore = (0, zustand_1.create)((set) => ({
    loading: false,
    error: null,
    setLoading: (loading) => set({ loading }),
    setError: (error) => set({ error }),
}));

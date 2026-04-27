"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = MainLayout;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const react_router_dom_1 = require("react-router-dom");
const framer_motion_1 = require("framer-motion");
const lucide_react_1 = require("lucide-react");
const sonner_1 = require("sonner");
const store_1 = require("../store");
const GROUP_ORDER = ['今天', '近 7 天', '更早'];
function getConversationGroup(createdAt) {
    const created = new Date(createdAt);
    const now = new Date();
    const diffMs = now.getTime() - created.getTime();
    const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000));
    if (diffDays <= 0)
        return '今天';
    if (diffDays <= 7)
        return '近 7 天';
    return '更早';
}
function MainLayout() {
    const [sidebarOpen, setSidebarOpen] = (0, react_1.useState)(false);
    const [sidebarCollapsed, setSidebarCollapsed] = (0, react_1.useState)(false);
    const [isEditing, setIsEditing] = (0, react_1.useState)(null);
    const [editTitle, setEditTitle] = (0, react_1.useState)('');
    const navigate = (0, react_router_dom_1.useNavigate)();
    const location = (0, react_router_dom_1.useLocation)();
    const isAuthenticated = (0, store_1.useAuthStore)((state) => state.isAuthenticated);
    const user = (0, store_1.useAuthStore)((state) => state.user);
    const logout = (0, store_1.useAuthStore)((state) => state.logout);
    const conversations = (0, store_1.useConversationStore)((state) => state.conversations);
    const currentConversation = (0, store_1.useConversationStore)((state) => state.currentConversation);
    const setCurrentConversation = (0, store_1.useConversationStore)((state) => state.setCurrentConversation);
    const fetchConversations = (0, store_1.useConversationStore)((state) => state.fetchConversations);
    const createConversation = (0, store_1.useConversationStore)((state) => state.createConversation);
    const updateConversation = (0, store_1.useConversationStore)((state) => state.updateConversation);
    const deleteConversation = (0, store_1.useConversationStore)((state) => state.deleteConversation);
    const loading = (0, store_1.useConversationStore)((state) => state.loading);
    (0, react_1.useEffect)(() => {
        if (!isAuthenticated)
            return;
        fetchConversations();
    }, [isAuthenticated, fetchConversations]);
    (0, react_1.useEffect)(() => {
        const conversationId = location.pathname.split('/')[1];
        if (!conversationId || conversationId === '') {
            setCurrentConversation(null);
            return;
        }
        const conversation = conversations.find((c) => c.id === conversationId);
        if (conversation) {
            setCurrentConversation(conversation);
        }
    }, [location.pathname, conversations, setCurrentConversation]);
    const groupedConversations = (0, react_1.useMemo)(() => {
        const groups = {
            今天: [],
            '近 7 天': [],
            更早: [],
        };
        conversations.forEach((conversation) => {
            groups[getConversationGroup(conversation.created_at)].push(conversation);
        });
        return groups;
    }, [conversations]);
    const handleNewConversation = async () => {
        try {
            const conversation = await createConversation('新对话');
            navigate(`/${conversation.id}`);
            setSidebarOpen(false);
            sonner_1.toast.success('已创建新对话');
        }
        catch {
            sonner_1.toast.error('创建会话失败');
        }
    };
    const handleSelectConversation = (conversation) => {
        setCurrentConversation(conversation);
        navigate(`/${conversation.id}`);
        setSidebarOpen(false);
    };
    const handleStartEdit = (conversation, e) => {
        e.stopPropagation();
        setIsEditing(conversation.id);
        setEditTitle(conversation.title);
    };
    const handleSaveEdit = async (id) => {
        if (!editTitle.trim()) {
            setIsEditing(null);
            return;
        }
        try {
            await updateConversation(id, editTitle.trim());
            sonner_1.toast.success('会话名称已更新');
        }
        catch {
            sonner_1.toast.error('更新会话名称失败');
        }
        finally {
            setIsEditing(null);
        }
    };
    const handleDeleteConversation = async (id, e) => {
        e.stopPropagation();
        if (!confirm('确定要删除这个会话吗？'))
            return;
        try {
            await deleteConversation(id);
            if (currentConversation?.id === id) {
                navigate('/');
            }
            sonner_1.toast.success('会话已删除');
        }
        catch {
            sonner_1.toast.error('删除会话失败');
        }
    };
    const handleLogout = async () => {
        try {
            await logout();
            navigate('/login');
            sonner_1.toast.success('已退出登录');
        }
        catch {
            sonner_1.toast.error('退出登录失败');
        }
    };
    return ((0, jsx_runtime_1.jsxs)("div", { className: "flex h-screen bg-slate-100 text-slate-900", children: [(0, jsx_runtime_1.jsx)(framer_motion_1.AnimatePresence, { children: sidebarOpen && ((0, jsx_runtime_1.jsx)(framer_motion_1.motion.div, { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, onClick: () => setSidebarOpen(false), className: "fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-[2px] lg:hidden" })) }), (0, jsx_runtime_1.jsxs)("aside", { className: 'fixed inset-y-0 left-0 z-50 flex w-80 flex-col border-r border-slate-200 bg-white shadow-2xl shadow-slate-950/5 transition-all lg:static lg:translate-x-0 ' +
                    (sidebarCollapsed ? 'lg:w-20 ' : 'lg:w-80 ') +
                    (sidebarOpen ? 'translate-x-0' : '-translate-x-full'), children: [(0, jsx_runtime_1.jsxs)("div", { className: "border-b border-slate-200/80 px-4 pb-4 pt-5", children: [(0, jsx_runtime_1.jsxs)("div", { className: "mb-4 flex items-center justify-between", children: [(0, jsx_runtime_1.jsxs)("div", { className: "flex items-center gap-3", children: [(0, jsx_runtime_1.jsx)("div", { className: "flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 shadow-lg shadow-indigo-500/30", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Bot, { className: "h-5 w-5 text-white" }) }), !sidebarCollapsed && ((0, jsx_runtime_1.jsxs)("div", { children: [(0, jsx_runtime_1.jsx)("p", { className: "text-base font-semibold leading-none", children: "\u77E5\u8BC6\u5E93\u95EE\u7B54" }), (0, jsx_runtime_1.jsx)("p", { className: "mt-1 text-xs text-slate-500", children: "Conversation Workspace" })] }))] }), (0, jsx_runtime_1.jsxs)("div", { className: "flex items-center gap-1", children: [(0, jsx_runtime_1.jsx)("button", { onClick: () => setSidebarCollapsed((prev) => !prev), className: "hidden rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:inline-flex", title: sidebarCollapsed ? '展开导航栏' : '收起导航栏', children: sidebarCollapsed ? (0, jsx_runtime_1.jsx)(lucide_react_1.PanelLeftOpen, { className: "h-5 w-5" }) : (0, jsx_runtime_1.jsx)(lucide_react_1.PanelLeftClose, { className: "h-5 w-5" }) }), (0, jsx_runtime_1.jsx)("button", { onClick: () => setSidebarOpen(false), className: "rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:hidden", children: (0, jsx_runtime_1.jsx)(lucide_react_1.X, { className: "h-5 w-5" }) })] })] }), (0, jsx_runtime_1.jsxs)("button", { onClick: handleNewConversation, className: `flex h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 text-sm font-medium text-white shadow-lg shadow-indigo-500/30 transition-all hover:-translate-y-0.5 hover:from-indigo-600 hover:to-indigo-700 ${sidebarCollapsed ? 'w-11' : 'w-full'}`, title: "\u65B0\u5EFA\u5BF9\u8BDD", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Plus, { className: "h-4 w-4" }), !sidebarCollapsed && '新建对话'] })] }), (0, jsx_runtime_1.jsx)("div", { className: "flex-1 overflow-y-auto px-3 py-4", children: loading ? ((0, jsx_runtime_1.jsx)("div", { className: "space-y-2 px-1", children: Array.from({ length: 6 }).map((_, i) => ((0, jsx_runtime_1.jsx)("div", { className: "h-14 animate-pulse rounded-xl bg-slate-100" }, i))) })) : conversations.length === 0 ? ((0, jsx_runtime_1.jsxs)("div", { className: "mx-2 mt-14 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.History, { className: "mx-auto mb-3 h-10 w-10 text-slate-300" }), (0, jsx_runtime_1.jsx)("p", { className: "text-sm font-medium text-slate-500", children: "\u6682\u65E0\u5339\u914D\u4F1A\u8BDD" }), (0, jsx_runtime_1.jsx)("p", { className: "mt-1 text-xs text-slate-400", children: "\u70B9\u51FB\u201C\u65B0\u5EFA\u5BF9\u8BDD\u201D\u5F00\u59CB\u63D0\u95EE" })] })) : ((0, jsx_runtime_1.jsx)("div", { className: "space-y-4", children: GROUP_ORDER.map((group) => {
                                const list = groupedConversations[group];
                                if (!list || list.length === 0)
                                    return null;
                                return ((0, jsx_runtime_1.jsxs)("section", { className: "space-y-2 px-1", children: [!sidebarCollapsed && ((0, jsx_runtime_1.jsxs)("div", { className: "flex items-center gap-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.CalendarDays, { className: "h-3.5 w-3.5" }), group] })), (0, jsx_runtime_1.jsx)("div", { className: "space-y-1.5", children: list.map((conversation) => {
                                                const active = currentConversation?.id === conversation.id;
                                                return ((0, jsx_runtime_1.jsx)(framer_motion_1.motion.div, { whileHover: { x: 2 }, onClick: () => handleSelectConversation(conversation), className: `group cursor-pointer rounded-xl border px-3 py-2.5 transition-all ${active
                                                        ? 'border-indigo-200 bg-indigo-50/80 shadow-sm'
                                                        : 'border-transparent hover:border-slate-200 hover:bg-slate-50'}`, children: isEditing === conversation.id ? ((0, jsx_runtime_1.jsx)("input", { autoFocus: true, value: editTitle, onChange: (e) => setEditTitle(e.target.value), onBlur: () => void handleSaveEdit(conversation.id), onKeyDown: (e) => e.key === 'Enter' && void handleSaveEdit(conversation.id), onClick: (e) => e.stopPropagation(), className: "h-8 w-full rounded-lg border border-indigo-300 px-2 text-sm outline-none ring-2 ring-indigo-100" })) : ((0, jsx_runtime_1.jsxs)(jsx_runtime_1.Fragment, { children: [(0, jsx_runtime_1.jsxs)("div", { className: "flex items-start justify-between gap-2", children: [(0, jsx_runtime_1.jsxs)("div", { className: "flex min-w-0 flex-1 items-center gap-2", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.MessageSquare, { className: `mt-0.5 h-4 w-4 flex-shrink-0 ${active ? 'text-indigo-500' : 'text-slate-400'}` }), !sidebarCollapsed && ((0, jsx_runtime_1.jsx)("span", { className: `truncate text-sm ${active ? 'font-medium text-indigo-700' : 'text-slate-700'}`, children: conversation.title }))] }), !sidebarCollapsed && ((0, jsx_runtime_1.jsxs)("div", { className: "hidden items-center gap-1 opacity-0 transition-opacity group-hover:flex group-hover:opacity-100", children: [(0, jsx_runtime_1.jsx)("button", { onClick: (e) => handleStartEdit(conversation, e), className: "rounded-md p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-700", "aria-label": "\u7F16\u8F91\u4F1A\u8BDD", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Edit3, { className: "h-3.5 w-3.5" }) }), (0, jsx_runtime_1.jsx)("button", { onClick: (e) => void handleDeleteConversation(conversation.id, e), className: "rounded-md p-1 text-slate-400 hover:bg-red-50 hover:text-red-600", "aria-label": "\u5220\u9664\u4F1A\u8BDD", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Trash2, { className: "h-3.5 w-3.5" }) })] }))] }), !sidebarCollapsed && ((0, jsx_runtime_1.jsx)("p", { className: "mt-1.5 text-[11px] text-slate-400", children: new Date(conversation.created_at).toLocaleDateString() }))] })) }, conversation.id));
                                            }) })] }, group));
                            }) })) }), (0, jsx_runtime_1.jsx)("div", { className: "border-t border-slate-200/80 p-4", children: (0, jsx_runtime_1.jsxs)("div", { className: "flex items-center justify-between gap-2 rounded-2xl bg-slate-100/80 px-3 py-2", children: [(0, jsx_runtime_1.jsxs)("div", { className: "flex min-w-0 items-center gap-3", children: [(0, jsx_runtime_1.jsx)("div", { className: "flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-sm font-semibold text-white", children: user?.phone?.slice(-2) || 'U' }), (0, jsx_runtime_1.jsxs)("div", { className: "min-w-0", children: [(0, jsx_runtime_1.jsx)("p", { className: "truncate text-sm font-medium text-slate-800", children: user?.phone || '用户' }), (0, jsx_runtime_1.jsx)("p", { className: "text-xs text-slate-500", children: "\u6807\u51C6\u6743\u9650" })] })] }), (0, jsx_runtime_1.jsx)("button", { onClick: () => void handleLogout(), className: "rounded-lg p-2 text-slate-500 transition-colors hover:bg-white hover:text-slate-700", title: "\u9000\u51FA\u767B\u5F55", children: (0, jsx_runtime_1.jsx)(lucide_react_1.LogOut, { className: "h-5 w-5" }) })] }) })] }), (0, jsx_runtime_1.jsxs)("main", { className: "flex min-w-0 flex-1 flex-col", children: [(0, jsx_runtime_1.jsx)("header", { className: "flex h-16 items-center border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur md:px-6", children: (0, jsx_runtime_1.jsxs)("div", { className: "flex min-w-0 items-center gap-3", children: [(0, jsx_runtime_1.jsx)("button", { onClick: () => setSidebarOpen(true), className: "rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 lg:hidden", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Menu, { className: "h-5 w-5" }) }), (0, jsx_runtime_1.jsx)("h2", { className: "truncate text-base font-semibold text-slate-900 md:text-lg", children: currentConversation?.title || '新对话' })] }) }), (0, jsx_runtime_1.jsx)("div", { className: "flex-1 overflow-hidden", children: (0, jsx_runtime_1.jsx)(react_router_dom_1.Outlet, {}) })] })] }));
}

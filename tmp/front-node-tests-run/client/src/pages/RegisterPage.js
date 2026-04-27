"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = RegisterPage;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const react_router_dom_1 = require("react-router-dom");
const framer_motion_1 = require("framer-motion");
const sonner_1 = require("sonner");
const lucide_react_1 = require("lucide-react");
const api_1 = require("../api");
const store_1 = require("../store");
function RegisterPage() {
    const [phone, setPhone] = (0, react_1.useState)('');
    const [password, setPassword] = (0, react_1.useState)('');
    const [confirmPassword, setConfirmPassword] = (0, react_1.useState)('');
    const [loading, setLoading] = (0, react_1.useState)(false);
    const navigate = (0, react_router_dom_1.useNavigate)();
    const register = (0, store_1.useAuthStore)((state) => state.register);
    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!phone || !password || !confirmPassword) {
            sonner_1.toast.error('请填写所有字段');
            return;
        }
        if (password !== confirmPassword) {
            sonner_1.toast.error('两次输入的密码不一致');
            return;
        }
        if (password.length < 8) {
            sonner_1.toast.error('密码长度至少 8 位');
            return;
        }
        if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password)) {
            sonner_1.toast.error('密码需包含大写字母、小写字母和数字');
            return;
        }
        setLoading(true);
        try {
            await register(phone, password);
            sonner_1.toast.success('注册成功');
            navigate('/');
        }
        catch (error) {
            sonner_1.toast.error((0, api_1.extractApiErrorMessage)(error, '注册失败，请稍后重试'));
        }
        finally {
            setLoading(false);
        }
    };
    return ((0, jsx_runtime_1.jsxs)("div", { className: "relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10", children: [(0, jsx_runtime_1.jsxs)("div", { className: "pointer-events-none absolute inset-0", children: [(0, jsx_runtime_1.jsx)("div", { className: "absolute left-[-80px] top-[-140px] h-80 w-80 rounded-full bg-emerald-500/22 blur-3xl" }), (0, jsx_runtime_1.jsx)("div", { className: "absolute -right-24 bottom-[-100px] h-80 w-80 rounded-full bg-indigo-500/26 blur-3xl" }), (0, jsx_runtime_1.jsx)("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_80%_20%,rgba(56,189,248,0.14),transparent_40%),radial-gradient(circle_at_30%_70%,rgba(16,185,129,0.12),transparent_45%)]" })] }), (0, jsx_runtime_1.jsx)(framer_motion_1.motion.div, { initial: { opacity: 0, y: 24 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, ease: 'easeOut' }, className: "relative z-10 w-full max-w-md", children: (0, jsx_runtime_1.jsxs)("div", { className: "rounded-3xl border border-white/15 bg-white/95 p-8 shadow-2xl shadow-slate-950/25 backdrop-blur", children: [(0, jsx_runtime_1.jsxs)("div", { className: "mb-8 text-center", children: [(0, jsx_runtime_1.jsx)("div", { className: "mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-indigo-600 shadow-lg shadow-emerald-500/30", children: (0, jsx_runtime_1.jsx)(lucide_react_1.User, { className: "h-7 w-7 text-white" }) }), (0, jsx_runtime_1.jsx)("h1", { className: "text-2xl font-semibold tracking-tight text-slate-900", children: "\u521B\u5EFA\u8D26\u53F7" }), (0, jsx_runtime_1.jsx)("p", { className: "mt-2 text-sm text-slate-500", children: "\u5B8C\u6210\u6CE8\u518C\u540E\u5373\u53EF\u5F00\u59CB\u77E5\u8BC6\u5E93\u95EE\u7B54\u4E0E\u4F1A\u8BDD\u7BA1\u7406\u3002" })] }), (0, jsx_runtime_1.jsxs)("form", { onSubmit: handleSubmit, className: "space-y-5", children: [(0, jsx_runtime_1.jsxs)("label", { className: "block space-y-2", children: [(0, jsx_runtime_1.jsx)("span", { className: "text-sm font-medium text-slate-700", children: "\u624B\u673A\u53F7" }), (0, jsx_runtime_1.jsxs)("div", { className: "group relative", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Phone, { className: "pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-emerald-500" }), (0, jsx_runtime_1.jsx)("input", { type: "tel", value: phone, onChange: (e) => setPhone(e.target.value), className: "h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-emerald-300 focus:bg-white focus:ring-4 focus:ring-emerald-100", placeholder: "\u8BF7\u8F93\u5165\u624B\u673A\u53F7", autoComplete: "tel" })] })] }), (0, jsx_runtime_1.jsxs)("label", { className: "block space-y-2", children: [(0, jsx_runtime_1.jsx)("span", { className: "text-sm font-medium text-slate-700", children: "\u5BC6\u7801" }), (0, jsx_runtime_1.jsxs)("div", { className: "group relative", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Lock, { className: "pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-emerald-500" }), (0, jsx_runtime_1.jsx)("input", { type: "password", value: password, onChange: (e) => setPassword(e.target.value), className: "h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-emerald-300 focus:bg-white focus:ring-4 focus:ring-emerald-100", placeholder: "\u81F3\u5C11 6 \u4F4D\u5BC6\u7801", autoComplete: "new-password" })] })] }), (0, jsx_runtime_1.jsxs)("label", { className: "block space-y-2", children: [(0, jsx_runtime_1.jsx)("span", { className: "text-sm font-medium text-slate-700", children: "\u786E\u8BA4\u5BC6\u7801" }), (0, jsx_runtime_1.jsxs)("div", { className: "group relative", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Lock, { className: "pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-emerald-500" }), (0, jsx_runtime_1.jsx)("input", { type: "password", value: confirmPassword, onChange: (e) => setConfirmPassword(e.target.value), className: "h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-emerald-300 focus:bg-white focus:ring-4 focus:ring-emerald-100", placeholder: "\u518D\u6B21\u8F93\u5165\u5BC6\u7801", autoComplete: "new-password" })] })] }), (0, jsx_runtime_1.jsx)("button", { type: "submit", disabled: loading, className: "flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-indigo-600 text-sm font-medium text-white shadow-lg shadow-emerald-500/30 transition-all hover:-translate-y-0.5 hover:from-emerald-600 hover:to-indigo-700 disabled:cursor-not-allowed disabled:opacity-60", children: loading ? ((0, jsx_runtime_1.jsxs)(jsx_runtime_1.Fragment, { children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Loader2, { className: "h-[18px] w-[18px] animate-spin" }), "\u6CE8\u518C\u4E2D..."] })) : ((0, jsx_runtime_1.jsxs)(jsx_runtime_1.Fragment, { children: ["\u7ACB\u5373\u6CE8\u518C", (0, jsx_runtime_1.jsx)(lucide_react_1.ArrowRight, { className: "h-[18px] w-[18px]" })] })) })] }), (0, jsx_runtime_1.jsxs)("p", { className: "mt-6 text-center text-sm text-slate-600", children: ["\u5DF2\u6709\u8D26\u53F7\uFF1F", (0, jsx_runtime_1.jsx)(react_router_dom_1.Link, { to: "/login", className: "ml-1 font-medium text-indigo-600 transition-colors hover:text-indigo-700", children: "\u53BB\u767B\u5F55" })] })] }) })] }));
}

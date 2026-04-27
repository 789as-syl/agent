"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = LoginPage;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const react_router_dom_1 = require("react-router-dom");
const framer_motion_1 = require("framer-motion");
const sonner_1 = require("sonner");
const lucide_react_1 = require("lucide-react");
const api_1 = require("../api");
const store_1 = require("../store");
function LoginPage() {
    const [phone, setPhone] = (0, react_1.useState)('');
    const [password, setPassword] = (0, react_1.useState)('');
    const [loading, setLoading] = (0, react_1.useState)(false);
    const navigate = (0, react_router_dom_1.useNavigate)();
    const login = (0, store_1.useAuthStore)((state) => state.login);
    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!phone || !password) {
            sonner_1.toast.error('请输入手机号和密码');
            return;
        }
        setLoading(true);
        try {
            await login(phone, password);
            sonner_1.toast.success('登录成功');
            navigate('/');
        }
        catch (error) {
            sonner_1.toast.error((0, api_1.extractApiErrorMessage)(error, '登录失败，请检查手机号和密码'));
        }
        finally {
            setLoading(false);
        }
    };
    return ((0, jsx_runtime_1.jsxs)("div", { className: "relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-10", children: [(0, jsx_runtime_1.jsxs)("div", { className: "pointer-events-none absolute inset-0", children: [(0, jsx_runtime_1.jsx)("div", { className: "absolute -left-24 top-[-120px] h-72 w-72 rounded-full bg-indigo-500/30 blur-3xl" }), (0, jsx_runtime_1.jsx)("div", { className: "absolute -right-20 bottom-[-120px] h-80 w-80 rounded-full bg-cyan-500/20 blur-3xl" }), (0, jsx_runtime_1.jsx)("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(99,102,241,0.18),transparent_40%),radial-gradient(circle_at_80%_80%,rgba(45,212,191,0.14),transparent_45%)]" })] }), (0, jsx_runtime_1.jsx)(framer_motion_1.motion.div, { initial: { opacity: 0, y: 24 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, ease: 'easeOut' }, className: "relative z-10 w-full max-w-md", children: (0, jsx_runtime_1.jsxs)("div", { className: "rounded-3xl border border-white/15 bg-white/95 p-8 shadow-2xl shadow-slate-950/25 backdrop-blur", children: [(0, jsx_runtime_1.jsxs)("div", { className: "mb-8 text-center", children: [(0, jsx_runtime_1.jsx)("div", { className: "mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-indigo-700 shadow-lg shadow-indigo-500/35", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Sparkles, { className: "h-7 w-7 text-white" }) }), (0, jsx_runtime_1.jsx)("h1", { className: "text-2xl font-semibold tracking-tight text-slate-900", children: "\u6B22\u8FCE\u56DE\u6765" }), (0, jsx_runtime_1.jsx)("p", { className: "mt-2 text-sm text-slate-500", children: "\u767B\u5F55\u4F60\u7684\u77E5\u8BC6\u5E93\u95EE\u7B54\u5DE5\u4F5C\u53F0\uFF0C\u7EE7\u7EED\u4E0A\u6B21\u5BF9\u8BDD\u3002" })] }), (0, jsx_runtime_1.jsxs)("form", { onSubmit: handleSubmit, className: "space-y-5", children: [(0, jsx_runtime_1.jsxs)("label", { className: "block space-y-2", children: [(0, jsx_runtime_1.jsx)("span", { className: "text-sm font-medium text-slate-700", children: "\u624B\u673A\u53F7" }), (0, jsx_runtime_1.jsxs)("div", { className: "group relative", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Phone, { className: "pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-indigo-500" }), (0, jsx_runtime_1.jsx)("input", { type: "tel", value: phone, onChange: (e) => setPhone(e.target.value), className: "h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100", placeholder: "\u8BF7\u8F93\u5165\u624B\u673A\u53F7", autoComplete: "tel" })] })] }), (0, jsx_runtime_1.jsxs)("label", { className: "block space-y-2", children: [(0, jsx_runtime_1.jsx)("span", { className: "text-sm font-medium text-slate-700", children: "\u5BC6\u7801" }), (0, jsx_runtime_1.jsxs)("div", { className: "group relative", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Lock, { className: "pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-indigo-500" }), (0, jsx_runtime_1.jsx)("input", { type: "password", value: password, onChange: (e) => setPassword(e.target.value), className: "h-12 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100", placeholder: "\u8BF7\u8F93\u5165\u5BC6\u7801", autoComplete: "current-password" })] })] }), (0, jsx_runtime_1.jsx)("button", { type: "submit", disabled: loading, className: "flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 text-sm font-medium text-white shadow-lg shadow-indigo-500/30 transition-all hover:-translate-y-0.5 hover:from-indigo-600 hover:to-indigo-700 disabled:cursor-not-allowed disabled:opacity-60", children: loading ? ((0, jsx_runtime_1.jsxs)(jsx_runtime_1.Fragment, { children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Loader2, { className: "h-[18px] w-[18px] animate-spin" }), "\u767B\u5F55\u4E2D..."] })) : ((0, jsx_runtime_1.jsxs)(jsx_runtime_1.Fragment, { children: ["\u767B\u5F55", (0, jsx_runtime_1.jsx)(lucide_react_1.ArrowRight, { className: "h-[18px] w-[18px]" })] })) })] }), (0, jsx_runtime_1.jsxs)("p", { className: "mt-6 text-center text-sm text-slate-600", children: ["\u8FD8\u6CA1\u6709\u8D26\u53F7\uFF1F", (0, jsx_runtime_1.jsx)(react_router_dom_1.Link, { to: "/register", className: "ml-1 font-medium text-indigo-600 transition-colors hover:text-indigo-700", children: "\u7ACB\u5373\u6CE8\u518C" })] })] }) })] }));
}

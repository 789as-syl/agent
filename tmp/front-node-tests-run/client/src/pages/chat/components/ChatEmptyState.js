"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = ChatEmptyState;
const jsx_runtime_1 = require("react/jsx-runtime");
const framer_motion_1 = require("framer-motion");
const lucide_react_1 = require("lucide-react");
function ChatEmptyState({ prompts, onSelectPrompt }) {
    return ((0, jsx_runtime_1.jsxs)("div", { className: "mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-6 text-center", children: [(0, jsx_runtime_1.jsxs)(framer_motion_1.motion.div, { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.45 }, children: [(0, jsx_runtime_1.jsx)("div", { className: "mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/30", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Sparkles, { className: "h-8 w-8 text-white" }) }), (0, jsx_runtime_1.jsx)("h2", { className: "text-2xl font-semibold tracking-tight text-slate-900", children: "\u5F00\u59CB\u4E00\u6B21\u77E5\u8BC6\u5E93\u95EE\u7B54" }), (0, jsx_runtime_1.jsx)("p", { className: "mt-2 text-sm leading-6 text-slate-500", children: "\u652F\u6301\u591A\u8F6E\u5BF9\u8BDD\u3001SSE \u6D41\u5F0F\u8F93\u51FA\u3001\u68C0\u7D22\u8FC7\u7A0B\u8FFD\u8E2A\u4E0E Markdown \u56DE\u7B54\u6E32\u67D3\u3002" })] }), (0, jsx_runtime_1.jsx)("div", { className: "mt-8 grid w-full gap-3 sm:grid-cols-2", children: prompts.map((prompt) => ((0, jsx_runtime_1.jsx)("button", { onClick: () => onSelectPrompt(prompt), className: "rounded-xl border border-slate-200 bg-white p-3 text-left text-sm text-slate-600 shadow-sm transition-all hover:-translate-y-0.5 hover:border-indigo-200 hover:text-slate-800", children: prompt }, prompt))) })] }));
}

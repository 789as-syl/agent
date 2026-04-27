"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = ChatMessageList;
const jsx_runtime_1 = require("react/jsx-runtime");
const framer_motion_1 = require("framer-motion");
const lucide_react_1 = require("lucide-react");
const react_markdown_1 = require("react-markdown");
const remark_gfm_1 = require("remark-gfm");
const ExecutionTraceDisplay_1 = require("../../../components/ExecutionTraceDisplay");
function ChatMessageList({ messages, isRunning, isReplaying = false, messagesEndRef, onRegenerate, }) {
    return ((0, jsx_runtime_1.jsxs)("div", { className: "mx-auto w-full max-w-4xl space-y-6", children: [(0, jsx_runtime_1.jsx)(framer_motion_1.AnimatePresence, { initial: false, children: messages.map((message, index) => {
                    const isUser = message.role === 'user';
                    const isLatestAssistant = !isUser && !messages.slice(index + 1).some((nextMessage) => nextMessage.role === 'assistant');
                    const canRegenerate = Boolean(!isUser && !isRunning && !isReplaying && isLatestAssistant && message.run_id && onRegenerate);
                    const isProgressiveAssistant = message.id === 'streaming-assistant' && (isRunning || isReplaying);
                    return ((0, jsx_runtime_1.jsxs)(framer_motion_1.motion.div, { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.24, delay: index * 0.03 }, className: `flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`, children: [!isUser && ((0, jsx_runtime_1.jsx)("div", { className: "mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-500/30", children: (0, jsx_runtime_1.jsx)(lucide_react_1.Bot, { className: "h-[18px] w-[18px]" }) })), (0, jsx_runtime_1.jsxs)("div", { className: `min-w-0 ${isUser ? 'max-w-[85%]' : 'max-w-[92%]'}`, children: [(0, jsx_runtime_1.jsx)("div", { className: `rounded-2xl border px-4 py-3 shadow-sm ${isUser
                                            ? 'border-indigo-500/30 bg-gradient-to-br from-indigo-500 to-indigo-600 text-white shadow-indigo-500/20'
                                            : 'border-slate-200 bg-white text-slate-800'}`, children: isUser ? ((0, jsx_runtime_1.jsx)("p", { className: "whitespace-pre-wrap text-[15px] leading-7", children: message.content })) : ((0, jsx_runtime_1.jsxs)("div", { className: "space-y-3", children: [message.raw_reasoning && message.raw_reasoning.trim() && ((0, jsx_runtime_1.jsxs)("div", { className: "overflow-hidden rounded-xl border border-violet-200 bg-violet-50/80", children: [(0, jsx_runtime_1.jsx)("div", { className: "border-b border-violet-200 px-3 py-2 text-xs font-semibold text-violet-700", children: "\u539F\u59CB reasoning \u6D41" }), (0, jsx_runtime_1.jsx)("pre", { className: "whitespace-pre-wrap px-3 py-3 text-[13px] leading-6 text-violet-950", children: message.raw_reasoning })] })), message.execution_trace && message.execution_trace.length > 0 && ((0, jsx_runtime_1.jsx)(ExecutionTraceDisplay_1.default, { trace: message.execution_trace, defaultExpanded: message.id === 'streaming-assistant' || isLatestAssistant })), isProgressiveAssistant ? ((0, jsx_runtime_1.jsx)("div", { className: "whitespace-pre-wrap text-[15px] leading-7 text-slate-700", children: resolveRenderableContent(message, true) })) : ((0, jsx_runtime_1.jsx)("div", { className: "max-w-none text-[15px] leading-7 text-slate-700 [&_a]:text-indigo-600 [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:border-indigo-200 [&_blockquote]:bg-indigo-50/40 [&_blockquote]:px-3 [&_blockquote]:py-2 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[13px] [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_p]:my-3 [&_pre]:my-4 [&_pre]:overflow-auto [&_pre]:rounded-xl [&_pre]:bg-slate-900 [&_pre]:p-4 [&_pre]:text-slate-200 [&_table]:my-4 [&_table]:w-full [&_table]:border-collapse [&_tbody_tr:nth-child(odd)]:bg-slate-50 [&_td]:border [&_td]:border-slate-200 [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-slate-200 [&_th]:bg-slate-100 [&_th]:px-3 [&_th]:py-2 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5", children: (0, jsx_runtime_1.jsx)(react_markdown_1.default, { remarkPlugins: [remark_gfm_1.default], children: resolveRenderableContent(message, isRunning) }) }))] })) }), (0, jsx_runtime_1.jsxs)("div", { className: `mt-2 flex items-center gap-2 text-xs text-slate-400 ${isUser ? 'justify-end' : 'justify-between'}`, children: [(0, jsx_runtime_1.jsx)("p", { className: isUser ? 'text-right' : 'text-left', children: new Date(message.created_at).toLocaleTimeString() }), canRegenerate && ((0, jsx_runtime_1.jsxs)("button", { onClick: () => void onRegenerate?.(message), className: "inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-500 transition-colors hover:border-indigo-200 hover:text-indigo-600", title: "\u57FA\u4E8E\u8FD9\u4E00\u8F6E\u56DE\u7B54\u91CD\u65B0\u751F\u6210", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.RotateCcw, { className: "h-3.5 w-3.5" }), "\u91CD\u65B0\u751F\u6210"] }))] })] }), isUser && ((0, jsx_runtime_1.jsx)("div", { className: "mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-slate-700 to-slate-800 text-white", children: (0, jsx_runtime_1.jsx)(lucide_react_1.User, { className: "h-[18px] w-[18px]" }) }))] }, message.id));
                }) }), (0, jsx_runtime_1.jsx)("div", { ref: messagesEndRef })] }));
}
function resolveRenderableContent(message, isRunning) {
    if (message.content && message.content.trim()) {
        return message.content;
    }
    const blocks = Array.isArray(message.content_blocks) ? message.content_blocks : [];
    if (blocks.length > 0) {
        return blocks
            .map((block) => {
            if (typeof block.text === 'string' && block.text.trim()) {
                return block.text;
            }
            try {
                return JSON.stringify(block, null, 2);
            }
            catch {
                return '';
            }
        })
            .filter((item) => item.trim().length > 0)
            .join('\n\n');
    }
    return isRunning ? '正在生成回答...' : '';
}

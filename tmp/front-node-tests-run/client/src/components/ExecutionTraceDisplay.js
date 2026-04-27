"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = ExecutionTraceDisplay;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const framer_motion_1 = require("framer-motion");
const lucide_react_1 = require("lucide-react");
function getTraceIcon(entry) {
    if (entry.status === 'error') {
        return (0, jsx_runtime_1.jsx)(lucide_react_1.ShieldAlert, { className: "h-4 w-4 text-rose-500" });
    }
    if (entry.status === 'running' || entry.status === 'pending') {
        return (0, jsx_runtime_1.jsx)(lucide_react_1.Loader2, { className: "h-4 w-4 animate-spin text-indigo-500" });
    }
    switch (entry.kind) {
        case 'reasoning':
            return (0, jsx_runtime_1.jsx)(lucide_react_1.Sparkles, { className: "h-4 w-4 text-violet-500" });
        case 'tool_start':
        case 'tool_progress':
        case 'tool_result':
            return (0, jsx_runtime_1.jsx)(lucide_react_1.CircleDashed, { className: "h-4 w-4 text-indigo-500" });
        default:
            return (0, jsx_runtime_1.jsx)(lucide_react_1.CheckCircle, { className: "h-4 w-4 text-emerald-500" });
    }
}
function getTraceStatusClass(entry) {
    if (entry.kind === 'reasoning') {
        return 'text-violet-700';
    }
    switch (entry.status) {
        case 'running':
        case 'pending':
            return 'text-indigo-600';
        case 'completed':
            return 'text-emerald-600';
        case 'error':
            return 'text-rose-600';
        default:
            return 'text-slate-500';
    }
}
function ExecutionTraceDisplay({ trace, title = '执行轨迹', defaultExpanded = false, }) {
    const [expanded, setExpanded] = (0, react_1.useState)(defaultExpanded);
    const [expandedItems, setExpandedItems] = (0, react_1.useState)(new Set());
    if (trace.length === 0)
        return null;
    return ((0, jsx_runtime_1.jsxs)("section", { className: "overflow-hidden rounded-xl border border-slate-200 bg-slate-50/80", children: [(0, jsx_runtime_1.jsxs)("button", { onClick: () => setExpanded((prev) => !prev), className: "flex w-full items-center justify-between px-3 py-2 text-left transition-colors hover:bg-slate-100", children: [(0, jsx_runtime_1.jsxs)("div", { className: "flex items-center gap-2 text-xs font-medium text-slate-600", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Sparkles, { className: "h-4 w-4 text-violet-500" }), title, " (", trace.length, ")"] }), (0, jsx_runtime_1.jsx)(lucide_react_1.ChevronDown, { className: `h-4 w-4 text-slate-400 transition-transform ${expanded ? '' : '-rotate-90'}` })] }), (0, jsx_runtime_1.jsx)(framer_motion_1.AnimatePresence, { initial: false, children: expanded && ((0, jsx_runtime_1.jsx)(framer_motion_1.motion.div, { initial: { height: 0, opacity: 0 }, animate: { height: 'auto', opacity: 1 }, exit: { height: 0, opacity: 0 }, transition: { duration: 0.2 }, className: "overflow-hidden", children: (0, jsx_runtime_1.jsx)("div", { className: "space-y-1.5 border-t border-slate-200 px-3 py-2", children: trace.map((entry) => {
                            const canExpand = Boolean(entry.detail);
                            const isItemExpanded = expandedItems.has(entry.id);
                            return ((0, jsx_runtime_1.jsxs)("div", { className: `rounded-lg p-2 ${entry.kind === 'reasoning'
                                    ? 'border border-violet-200 bg-violet-50/80'
                                    : 'bg-white/70'}`, children: [(0, jsx_runtime_1.jsxs)("button", { disabled: !canExpand, onClick: () => {
                                            if (!canExpand)
                                                return;
                                            setExpandedItems((prev) => {
                                                const next = new Set(prev);
                                                if (next.has(entry.id))
                                                    next.delete(entry.id);
                                                else
                                                    next.add(entry.id);
                                                return next;
                                            });
                                        }, className: `flex w-full items-start gap-2 text-left ${canExpand ? 'cursor-pointer' : 'cursor-default'}`, children: [(0, jsx_runtime_1.jsx)("span", { className: "mt-0.5", children: getTraceIcon(entry) }), (0, jsx_runtime_1.jsx)("div", { className: "min-w-0 flex-1", children: (0, jsx_runtime_1.jsx)("p", { className: `truncate text-xs font-semibold ${getTraceStatusClass(entry)}`, children: entry.kind === 'reasoning' ? `= ${entry.title}` : entry.title }) }), canExpand && ((0, jsx_runtime_1.jsx)(lucide_react_1.ChevronRight, { className: `mt-0.5 h-3.5 w-3.5 text-slate-400 transition-transform ${isItemExpanded ? 'rotate-90' : ''}` }))] }), (0, jsx_runtime_1.jsx)(framer_motion_1.AnimatePresence, { initial: false, children: isItemExpanded && entry.detail && ((0, jsx_runtime_1.jsx)(framer_motion_1.motion.pre, { initial: { height: 0, opacity: 0 }, animate: { height: 'auto', opacity: 1 }, exit: { height: 0, opacity: 0 }, transition: { duration: 0.18 }, className: "mt-2 overflow-hidden whitespace-pre-wrap rounded-md bg-slate-900 p-2 text-[11px] leading-5 text-slate-200", children: entry.detail })) })] }, entry.id));
                        }) }) })) })] }));
}

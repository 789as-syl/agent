import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle, ChevronDown, ChevronRight, CircleDashed, Loader2, ShieldAlert, Sparkles } from 'lucide-react'

import type { ExecutionTraceEntry } from '../types'

function getTraceIcon(entry: ExecutionTraceEntry) {
  if (entry.status === 'error') {
    return <ShieldAlert className="h-4 w-4 text-rose-500" />
  }
  if (entry.status === 'running' || entry.status === 'pending') {
    return <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
  }
  switch (entry.kind) {
    case 'scope_check':
    case 'decision':
    case 'clarification':
    case 'reasoning':
      return <Sparkles className="h-4 w-4 text-violet-500" />
    case 'tool_call':
    case 'tool_start':
    case 'tool_progress':
    case 'tool_result':
      return <CircleDashed className="h-4 w-4 text-indigo-500" />
    default:
      return <CheckCircle className="h-4 w-4 text-emerald-500" />
  }
}

function getTraceStatusClass(entry: ExecutionTraceEntry) {
  if (entry.kind === 'reasoning' || entry.kind === 'scope_check' || entry.kind === 'decision' || entry.kind === 'clarification') {
    return 'text-violet-700'
  }
  switch (entry.status) {
    case 'running':
    case 'pending':
      return 'text-indigo-600'
    case 'completed':
      return 'text-emerald-600'
    case 'error':
      return 'text-rose-600'
    default:
      return 'text-slate-500'
  }
}

export default function ExecutionTraceDisplay({
  trace,
  title = '执行轨迹',
  defaultExpanded = false,
}: {
  trace: ExecutionTraceEntry[]
  title?: string
  defaultExpanded?: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set())
  const visibleTrace = useMemo(
    () => trace.filter((entry) => (
      entry.kind !== 'reasoning'
      && entry.decision_code !== 'direct_answer'
    )),
    [trace]
  )

  if (visibleTrace.length === 0) return null

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50/80">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between px-3 py-2 text-left transition-colors hover:bg-slate-100"
      >
        <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
          <Sparkles className="h-4 w-4 text-violet-500" />
          {title} ({visibleTrace.length})
        </div>
        <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${expanded ? '' : '-rotate-90'}`} />
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-1.5 border-t border-slate-200 px-3 py-2">
              {visibleTrace.map((entry) => {
                const canExpand = Boolean(
                  entry.detail
                  || entry.reasoning_anchor
                  || entry.evidence?.some((evidence) => Boolean(evidence.detail))
                )
                const isItemExpanded = expandedItems.has(entry.id)

                return (
                  <div
                    key={entry.id}
                    className={`rounded-lg p-2 ${
                      entry.kind === 'reasoning'
                        ? 'border border-violet-200 bg-violet-50/80'
                        : 'bg-white/70'
                    }`}
                  >
                    <button
                      disabled={!canExpand}
                      onClick={() => {
                        if (!canExpand) return
                        setExpandedItems((prev) => {
                          const next = new Set(prev)
                          if (next.has(entry.id)) next.delete(entry.id)
                          else next.add(entry.id)
                          return next
                        })
                      }}
                      className={`flex w-full items-start gap-2 text-left ${canExpand ? 'cursor-pointer' : 'cursor-default'}`}
                    >
                      <span className="mt-0.5">{getTraceIcon(entry)}</span>
                      <div className="min-w-0 flex-1">
                        <p className={`truncate text-xs font-semibold ${getTraceStatusClass(entry)}`}>
                          {entry.title}
                        </p>
                        {entry.evidence && entry.evidence.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {entry.evidence.slice(0, 3).map((evidence, index) => (
                              <span
                                key={`${entry.id}-evidence-${index}`}
                                className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] text-slate-500"
                                title={evidence.detail || evidence.label}
                              >
                                {evidence.label}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      {canExpand && (
                        <ChevronRight
                          className={`mt-0.5 h-3.5 w-3.5 text-slate-400 transition-transform ${isItemExpanded ? 'rotate-90' : ''}`}
                        />
                      )}
                    </button>

                    <AnimatePresence initial={false}>
                      {isItemExpanded && entry.detail && (
                        <motion.pre
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.18 }}
                          className="mt-2 overflow-hidden whitespace-pre-wrap rounded-md bg-slate-900 p-2 text-[11px] leading-5 text-slate-200"
                        >
                          {entry.detail}
                        </motion.pre>
                      )}
                    </AnimatePresence>
                    <AnimatePresence initial={false}>
                      {isItemExpanded && entry.evidence?.some((evidence) => Boolean(evidence.detail)) && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.18 }}
                          className="mt-2 space-y-1 rounded-md border border-slate-200 bg-white px-2 py-2 text-[11px] text-slate-600"
                        >
                          {entry.evidence.map((evidence, index) => (
                            <div key={`${entry.id}-evidence-detail-${index}`}>
                              <span className="font-medium text-slate-700">{evidence.label}</span>
                              {evidence.detail ? `：${evidence.detail}` : ''}
                            </div>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                    <AnimatePresence initial={false}>
                      {isItemExpanded && entry.reasoning_anchor && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.18 }}
                          className="mt-2 rounded-md border border-slate-200 bg-slate-100 px-2 py-1 text-[11px] text-slate-600"
                        >
                          关联 reasoning 区间：{entry.reasoning_anchor.start} - {entry.reasoning_anchor.end}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

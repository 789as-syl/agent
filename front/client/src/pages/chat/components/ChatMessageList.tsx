import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Bot, CheckCircle2, HelpCircle, Info, RotateCcw, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import ExecutionTraceDisplay from '../../../components/ExecutionTraceDisplay'
import type { Message } from '../../../types'
import AssistantEvidencePanel from './AssistantEvidencePanel'
import AssistantMessageFeedback from './AssistantMessageFeedback'
import { getTraceAnswerBasis, resolveRenderableContent } from '../message-utils'
import type { AnswerBasis } from '../streaming-session'

interface ChatMessageListProps {
  messages: Message[]
  isRunning: boolean
  isReplaying?: boolean
  messagesEndRef: React.RefObject<HTMLDivElement | null>
  onRegenerate?: (message: Message) => Promise<boolean>
}

const RUN_STATE_COPY: Record<AnswerBasis, {
  title: string
  detail: string
  className: string
  icon: React.ReactNode
}> = {
  knowledge_backed: {
    title: '已基于知识库证据回答',
    detail: '下方证据卡片展示本轮回答使用的关键来源。',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    icon: <CheckCircle2 className="h-4 w-4 text-emerald-600" />,
  },
  direct: {
    title: '直接回答（未使用知识库证据）',
    detail: '本轮没有检索到或调用知识库证据，请按通用回答理解。',
    className: 'border-sky-200 bg-sky-50 text-sky-800',
    icon: <Info className="h-4 w-4 text-sky-600" />,
  },
  retrieval_unavailable: {
    title: '知识库检索不可用',
    detail: '回答已降级，建议稍后重试或补充上下文。',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
    icon: <AlertTriangle className="h-4 w-4 text-amber-600" />,
  },
  evidence_insufficient: {
    title: '知识库证据不足',
    detail: '目前证据不足以完整支撑回答，结论需要谨慎使用。',
    className: 'border-orange-200 bg-orange-50 text-orange-800',
    icon: <AlertTriangle className="h-4 w-4 text-orange-600" />,
  },
  needs_clarification: {
    title: '需要补充信息',
    detail: '请根据提示补充问题背景或确认下一步。',
    className: 'border-violet-200 bg-violet-50 text-violet-800',
    icon: <HelpCircle className="h-4 w-4 text-violet-600" />,
  },
}

function AssistantRunState({
  message,
  isProgressive,
}: {
  message: Message
  isProgressive: boolean
}) {
  const answerBasis = getTraceAnswerBasis(message.execution_trace)

  if (!answerBasis) {
    if (!isProgressive) return null
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
        <div className="flex items-center gap-2 font-semibold">
          <Info className="h-4 w-4" />
          正在组织回答
        </div>
        <p className="mt-1 leading-5">过程、正文和证据会随本轮运行更新。</p>
      </div>
    )
  }

  const copy = RUN_STATE_COPY[answerBasis]
  return (
    <div className={`rounded-xl border px-3 py-2 text-xs ${copy.className}`}>
      <div className="flex items-center gap-2 font-semibold">
        {copy.icon}
        {copy.title}
      </div>
      <p className="mt-1 leading-5 opacity-90">{copy.detail}</p>
    </div>
  )
}

export default function ChatMessageList({
  messages,
  isRunning,
  isReplaying = false,
  messagesEndRef,
  onRegenerate,
}: ChatMessageListProps) {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <AnimatePresence initial={false}>
        {messages.map((message, index) => {
          const isUser = message.role === 'user'
          const isLatestAssistant =
            !isUser && !messages.slice(index + 1).some((nextMessage) => nextMessage.role === 'assistant')
          const canRegenerate = Boolean(!isUser && !isRunning && !isReplaying && isLatestAssistant && message.run_id && onRegenerate)
          const isProgressiveAssistant = message.id === 'streaming-assistant' && (isRunning || isReplaying)
          return (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.24, delay: index * 0.03 }}
              className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              {!isUser && (
                <div className="mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-500/30">
                  <Bot className="h-[18px] w-[18px]" />
                </div>
              )}

              <div className={`min-w-0 ${isUser ? 'max-w-[85%]' : 'max-w-[92%]'}`}>
                <div
                  className={`rounded-2xl border px-4 py-3 shadow-sm ${
                    isUser
                      ? 'border-indigo-500/30 bg-gradient-to-br from-indigo-500 to-indigo-600 text-white shadow-indigo-500/20'
                      : 'border-slate-200 bg-white text-slate-800'
                  }`}
                >
                  {isUser ? (
                    <p className="whitespace-pre-wrap text-[15px] leading-7">{message.content}</p>
                  ) : (
                    <div className="space-y-3">
                      <AssistantRunState message={message} isProgressive={isProgressiveAssistant} />

                      {message.execution_trace && message.execution_trace.length > 0 && (
                        <ExecutionTraceDisplay
                          trace={message.execution_trace}
                          defaultExpanded={message.id === 'streaming-assistant' || isLatestAssistant}
                        />
                      )}

                      {isProgressiveAssistant ? (
                        <div className="whitespace-pre-wrap text-[15px] leading-7 text-slate-700">
                          {resolveRenderableContent(message, true)}
                        </div>
                      ) : (
                        <div className="max-w-none text-[15px] leading-7 text-slate-700 [&_a]:text-indigo-600 [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:border-indigo-200 [&_blockquote]:bg-indigo-50/40 [&_blockquote]:px-3 [&_blockquote]:py-2 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[13px] [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_p]:my-3 [&_pre]:my-4 [&_pre]:overflow-auto [&_pre]:rounded-xl [&_pre]:bg-slate-900 [&_pre]:p-4 [&_pre]:text-slate-200 [&_table]:my-4 [&_table]:w-full [&_table]:border-collapse [&_tbody_tr:nth-child(odd)]:bg-slate-50 [&_td]:border [&_td]:border-slate-200 [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-slate-200 [&_th]:bg-slate-100 [&_th]:px-3 [&_th]:py-2 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {resolveRenderableContent(message, isRunning)}
                          </ReactMarkdown>
                        </div>
                      )}

                      {!isProgressiveAssistant && (
                        <AssistantEvidencePanel trace={message.execution_trace} />
                      )}
                    </div>
                  )}
                </div>

                <div className={`mt-2 flex items-center gap-2 text-xs text-slate-400 ${isUser ? 'justify-end' : 'justify-between'}`}>
                  <div className={`flex flex-wrap items-center gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <p className={isUser ? 'text-right' : 'text-left'}>
                      {new Date(message.created_at).toLocaleTimeString()}
                    </p>
                    {!isUser && message.id !== 'streaming-assistant' && <AssistantMessageFeedback messageId={message.id} />}
                  </div>
                  <div className="flex items-center gap-2">
                    {canRegenerate && (
                      <button
                        onClick={() => void onRegenerate?.(message)}
                        className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-500 transition-colors hover:border-indigo-200 hover:text-indigo-600"
                        title="基于这一轮回答重新生成"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        重新生成
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {isUser && (
                <div className="mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-slate-700 to-slate-800 text-white">
                  <User className="h-[18px] w-[18px]" />
                </div>
              )}
            </motion.div>
          )
        })}
      </AnimatePresence>
      <div ref={messagesEndRef} />
    </div>
  )
}

import { AnimatePresence, motion } from 'framer-motion'
import { Bot, RotateCcw, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import ExecutionTraceDisplay from '../../../components/ExecutionTraceDisplay'
import type { Message } from '../../../types'
import { resolveRenderableContent } from '../message-utils'

interface ChatMessageListProps {
  messages: Message[]
  isRunning: boolean
  isReplaying?: boolean
  messagesEndRef: React.RefObject<HTMLDivElement | null>
  onRegenerate?: (message: Message) => Promise<boolean>
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
                    </div>
                  )}
                </div>

                <div className={`mt-2 flex items-center gap-2 text-xs text-slate-400 ${isUser ? 'justify-end' : 'justify-between'}`}>
                  <p className={isUser ? 'text-right' : 'text-left'}>
                    {new Date(message.created_at).toLocaleTimeString()}
                  </p>
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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowDown, Wand2 } from 'lucide-react'

import { useConversationStore } from '../store'
import type { HitlDecisionType } from '../types'
import { isBusyChatRunPhase } from './chat/chat-run-machine'
import ChatComposer from './chat/components/ChatComposer'
import ChatEmptyState from './chat/components/ChatEmptyState'
import ChatMessageList from './chat/components/ChatMessageList'
import { useChatRunController } from './chat/useChatRunController'

const SUGGESTED_PROMPTS = [
  '请总结机器学习和深度学习的区别',
  '帮我根据题库生成 5 道测试题',
  '列出最近一周检索命中率变化原因',
  '解释这段知识点的核心概念',
]

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesScrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const autoScrollRef = useRef(true)

  const [input, setInput] = useState('')
  const [hitlInput, setHitlInput] = useState('')
  const [showJumpToBottom, setShowJumpToBottom] = useState(false)

  const activeConversationId = id && id !== '' ? id : null
  const messages = useConversationStore((state) => state.messages)
  const fetchMessages = useConversationStore((state) => state.fetchMessages)
  const createConversation = useConversationStore((state) => state.createConversation)

  const {
    controller,
    displayMessages,
    composerStatusText,
    submittingHitl,
    sendMessage,
    interruptRun,
    retryRun,
    regenerateFromMessage,
    submitHitlDecision,
  } = useChatRunController({
    conversationId: activeConversationId,
    messages,
    fetchMessages,
    createConversation,
    navigateToConversation: (conversationId) => navigate(`/${conversationId}`),
  })

  const isChatBusy = useMemo(
    () => controller.isReplaying || isBusyChatRunPhase(controller.phase) || controller.phase === 'waiting_hitl',
    [controller.isReplaying, controller.phase],
  )

  const updateAutoScrollState = useCallback(() => {
    const container = messagesScrollRef.current
    if (!container) {
      autoScrollRef.current = true
      setShowJumpToBottom(false)
      return true
    }
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    const isNearBottom = distanceFromBottom < 96
    autoScrollRef.current = isNearBottom
    setShowJumpToBottom(!isNearBottom)
    return isNearBottom
  }, [])

  const scrollToMessageBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior })
    autoScrollRef.current = true
    setShowJumpToBottom(false)
  }, [])

  const handleSendMessage = useCallback(async () => {
    const normalized = input.trim()
    if (!normalized || isChatBusy) return

    autoScrollRef.current = true
    setShowJumpToBottom(false)
    const started = await sendMessage(normalized)
    if (started) {
      setInput('')
      setHitlInput('')
    }
  }, [input, isChatBusy, sendMessage])

  const handleRetry = useCallback(async () => {
    await retryRun()
  }, [retryRun])

  const handleInterrupt = useCallback(async () => {
    await interruptRun()
  }, [interruptRun])

  const handleSubmitHitl = useCallback(async (type: HitlDecisionType) => {
    const submitted = await submitHitlDecision(type, hitlInput)
    if (submitted) {
      setHitlInput('')
    }
  }, [hitlInput, submitHitlDecision])

  useEffect(() => {
    if (!autoScrollRef.current) return
    scrollToMessageBottom(isChatBusy ? 'auto' : 'smooth')
  }, [controller.session.assistantContent, controller.session.executionTrace, controller.session.hitl, displayMessages, isChatBusy, scrollToMessageBottom])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input])

  const hitlActions = controller.session.hitl?.allowed_actions || []

  return (
    <div className="flex h-full bg-slate-100">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-slate-200/80 bg-white/80 px-4 py-3 backdrop-blur lg:px-6">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <Wand2 className="h-4 w-4 text-indigo-500" />
            AI 知识检索已启用
          </div>
        </div>

        {controller.session.hitl?.pending && controller.runId && activeConversationId && (
          <div className="border-b border-cyan-200 bg-cyan-50/80 px-4 py-3 text-xs text-cyan-900 lg:px-6">
            <div className="mx-auto flex max-w-4xl flex-col gap-3">
              <div>
                <p className="text-sm font-semibold">HITL 待处理</p>
                <p className="mt-1 whitespace-pre-wrap text-xs leading-6">
                  {controller.session.hitl.prompt || '请补充必要信息后继续。'}
                </p>
              </div>

              {(hitlActions.includes('respond') || hitlActions.includes('edit')) && (
                <textarea
                  value={hitlInput}
                  onChange={(event) => setHitlInput(event.target.value)}
                  placeholder={hitlActions.includes('edit') ? '输入编辑后的内容…' : '输入补充说明…'}
                  className="min-h-[80px] rounded-xl border border-cyan-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-cyan-400"
                />
              )}

              <div className="flex flex-wrap items-center gap-2">
                {hitlActions.includes('respond') && (
                  <button
                    onClick={() => void handleSubmitHitl('respond')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-cyan-200 bg-white px-3 py-1.5 text-xs font-medium text-cyan-700 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    提交回应
                  </button>
                )}
                {hitlActions.includes('approve') && (
                  <button
                    onClick={() => void handleSubmitHitl('approve')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    通过
                  </button>
                )}
                {hitlActions.includes('edit') && (
                  <button
                    onClick={() => void handleSubmitHitl('edit')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    提交编辑
                  </button>
                )}
                {hitlActions.includes('reject') && (
                  <button
                    onClick={() => void handleSubmitHitl('reject')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    拒绝
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <div
          ref={messagesScrollRef}
          onScroll={updateAutoScrollState}
          className="relative flex-1 overflow-y-auto px-4 py-5 lg:px-6"
        >
          {displayMessages.length === 0 ? (
            <ChatEmptyState prompts={SUGGESTED_PROMPTS} onSelectPrompt={setInput} />
          ) : (
            <ChatMessageList
              messages={displayMessages}
              isRunning={isChatBusy}
              isReplaying={controller.isReplaying}
              messagesEndRef={messagesEndRef}
              onRegenerate={regenerateFromMessage}
            />
          )}
          {showJumpToBottom && displayMessages.length > 0 && (
            <button
              type="button"
              onClick={() => scrollToMessageBottom('smooth')}
              className="sticky bottom-4 left-1/2 z-10 mx-auto flex -translate-x-1/2 items-center gap-1 rounded-full border border-indigo-100 bg-white/95 px-3 py-1.5 text-xs font-medium text-indigo-600 shadow-lg shadow-slate-900/10 backdrop-blur transition-colors hover:border-indigo-200 hover:bg-indigo-50"
            >
              <ArrowDown className="h-3.5 w-3.5" />
              回到底部
            </button>
          )}
        </div>

        <ChatComposer
          input={input}
          isRunning={isChatBusy}
          hasMessages={displayMessages.length > 0 || Boolean(controller.session.pendingUserMessage)}
          retryTitle="继续 / 重试 / 重新生成"
          statusText={composerStatusText}
          textareaRef={textareaRef}
          onInputChange={setInput}
          onSend={handleSendMessage}
          onRetry={handleRetry}
          onInterrupt={handleInterrupt}
        />
      </div>
    </div>
  )
}

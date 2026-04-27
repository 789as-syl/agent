import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowDown, Wand2 } from 'lucide-react'
import { toast } from 'sonner'

import { chatRunsApi, sseClient } from '../api'
import { useChatStore, useConversationStore } from '../store'
import type { ChatRunStatusResponse, HitlDecisionType, Message, SSEEvent } from '../types'
import { buildDisplayMessages, hydrateMessages } from './chat/message-utils'
import {
  clearChatRunSnapshot,
  loadChatRunSnapshot,
  saveChatRunSnapshot,
} from './chat/session-persistence'
import ChatComposer from './chat/components/ChatComposer'
import ChatEmptyState from './chat/components/ChatEmptyState'
import ChatMessageList from './chat/components/ChatMessageList'
import {
  applyStreamingEvent,
  createStreamingSessionState,
  playbackStreamingEvents,
  restoreStreamingSessionFromRun,
  type PendingUserMessage,
} from './chat/streaming-session'

const SUGGESTED_PROMPTS = [
  '请总结机器学习和深度学习的区别',
  '帮我根据题库生成 5 道测试题',
  '列出最近一周检索命中率变化原因',
  '解释这段知识点的核心概念',
]

function buildPendingUserMessage(content: string): PendingUserMessage {
  return {
    id: `pending-user-${Date.now()}`,
    content,
    created_at: new Date().toISOString(),
  }
}

function resolvePendingUserMessage(
  query: string | null | undefined,
  existing?: PendingUserMessage | null,
): PendingUserMessage | null {
  if (existing) return existing
  const normalized = query?.trim()
  if (!normalized) return null
  return buildPendingUserMessage(normalized)
}

function isActiveRunStatus(status: string) {
  return status === 'pending' || status === 'running'
}

interface PlaybackEventsLoadResult {
  events: SSEEvent[]
  mode: 'none' | 'full' | 'delta'
  lastEventId: string | null
}

const PLAYBACK_REPLAY_INTERVAL_MS = 16
const PLAYBACK_REPLAY_BATCH_SIZE = 4
type StreamingSession = ReturnType<typeof createStreamingSessionState>

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesScrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const snapshotPersistTimerRef = useRef<number | null>(null)
  const activeConversationIdRef = useRef<string | null>(id && id !== '' ? id : null)
  const autoScrollRef = useRef(true)

  const [input, setInput] = useState('')
  const [hitlInput, setHitlInput] = useState('')
  const [submittingHitl, setSubmittingHitl] = useState(false)
  const [snapshotRunId, setSnapshotRunId] = useState<string | null>(null)
  const [snapshotLastEventId, setSnapshotLastEventId] = useState<string | null>(null)
  const [showJumpToBottom, setShowJumpToBottom] = useState(false)

  const messages = useConversationStore((state) => state.messages)
  const fetchMessages = useConversationStore((state) => state.fetchMessages)
  const addMessage = useConversationStore((state) => state.addMessage)
  const createConversation = useConversationStore((state) => state.createConversation)

  const {
    currentRunId,
    isRunning,
    setCurrentRunId,
    setIsRunning,
    clearChat,
  } = useChatStore()

  const [streamingSession, setStreamingSession] = useState(createStreamingSessionState())
  const streamingSessionRef = useRef(createStreamingSessionState())
  const terminalResolutionRunRef = useRef<string | null>(null)
  const replayTimerRef = useRef<number | null>(null)
  const replayResolverRef = useRef<((state: StreamingSession) => void) | null>(null)
  const [isReplaying, setIsReplaying] = useState(false)

  const updateStreamingSession = useCallback((
    updater: (
      current: StreamingSession
    ) => StreamingSession
  ) => {
    const nextState = updater(streamingSessionRef.current)
    streamingSessionRef.current = nextState
    setStreamingSession(nextState)
    return nextState
  }, [])

  const replaceStreamingSession = useCallback((nextState: StreamingSession) => {
    streamingSessionRef.current = nextState
    setStreamingSession(nextState)
  }, [])

  const resetStreamingSession = useCallback((pendingUserMessage: PendingUserMessage | null = null) => {
    replaceStreamingSession(createStreamingSessionState(pendingUserMessage))
  }, [replaceStreamingSession])

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


  const persistChatRunSnapshot = useCallback((
    conversationId: string,
    runId: string | null,
    sessionState: StreamingSession,
    lastEventId?: string | null,
  ) => {
    const resolvedLastEventId = lastEventId ?? sseClient.getLastEventId() ?? null
    setSnapshotRunId(runId)
    setSnapshotLastEventId(resolvedLastEventId)
    saveChatRunSnapshot({
      conversationId,
      runId,
      lastEventId: resolvedLastEventId,
      session: sessionState,
    })
  }, [])

  const stopPlaybackReplay = useCallback(() => {
    if (replayTimerRef.current) {
      window.clearTimeout(replayTimerRef.current)
      replayTimerRef.current = null
    }
    if (replayResolverRef.current) {
      const resolve = replayResolverRef.current
      replayResolverRef.current = null
      resolve(streamingSessionRef.current)
    }
    setIsReplaying(false)
  }, [])

  const stopStreamingRun = useCallback((
    options: {
      clearSession?: boolean
      clearSnapshotRunId?: boolean
    } = {}
  ) => {
    const { clearSession = false, clearSnapshotRunId = false } = options
    stopPlaybackReplay()
    sseClient.disconnect()
    setIsRunning(false)
    setCurrentRunId(null)
    if (clearSnapshotRunId) {
      setSnapshotRunId(null)
      setSnapshotLastEventId(null)
    }
    if (clearSession) {
      resetStreamingSession()
    }
  }, [resetStreamingSession, setCurrentRunId, setIsRunning, stopPlaybackReplay])

  const replayPlaybackEventsIncrementally = useCallback((
    baseState: StreamingSession,
    events: SSEEvent[],
  ): Promise<StreamingSession> => {
    stopPlaybackReplay()
    replaceStreamingSession(baseState)
    if (events.length === 0) {
      return Promise.resolve(baseState)
    }

    return new Promise((resolve) => {
      let eventIndex = 0
      setIsReplaying(true)
      replayResolverRef.current = resolve

      const finishReplay = (finalState: StreamingSession) => {
        if (replayTimerRef.current) {
          window.clearTimeout(replayTimerRef.current)
          replayTimerRef.current = null
        }
        replayResolverRef.current = null
        setIsReplaying(false)
        resolve(finalState)
      }

      const tick = () => {
        const batch = events.slice(eventIndex, eventIndex + PLAYBACK_REPLAY_BATCH_SIZE)
        if (batch.length === 0) {
          finishReplay(streamingSessionRef.current)
          return
        }

        const nextState = playbackStreamingEvents(streamingSessionRef.current, batch)
        replaceStreamingSession(nextState)
        eventIndex += batch.length

        if (eventIndex >= events.length) {
          finishReplay(nextState)
          return
        }

        replayTimerRef.current = window.setTimeout(tick, PLAYBACK_REPLAY_INTERVAL_MS)
      }

      tick()
    })
  }, [replaceStreamingSession, stopPlaybackReplay])

  const restoreSessionFromPlayback = useCallback(async (
    fallbackUserMessage: PendingUserMessage | null,
    runtimeState: ChatRunStatusResponse['runtime_state'] | undefined,
    existingState: StreamingSession | null,
    playback: PlaybackEventsLoadResult,
  ): Promise<StreamingSession> => {
    const baseState = restoreStreamingSessionFromRun(
      fallbackUserMessage,
      runtimeState,
      playback.mode === 'full' ? null : existingState,
      playback.mode === 'full' ? [] : playback.events,
    )

    if (playback.mode === 'full' && playback.events.length > 0) {
      return replayPlaybackEventsIncrementally(baseState, playback.events)
    }

    replaceStreamingSession(baseState)
    return baseState
  }, [replaceStreamingSession, replayPlaybackEventsIncrementally])

  const fetchMessagesSafely = useCallback(async (conversationId: string) => {
    try {
      await fetchMessages(conversationId)
      return true
    } catch {
      return false
    }
  }, [fetchMessages])


  const isActiveConversation = useCallback((conversationId: string) => (
    activeConversationIdRef.current === conversationId
  ), [])

  const loadPlaybackEvents = useCallback(async (
    conversationId: string,
    run: ChatRunStatusResponse,
    afterEventId?: string | null,
  ): Promise<PlaybackEventsLoadResult> => {
    const fetchFullPlayback = async (): Promise<PlaybackEventsLoadResult> => {
      try {
        const playback = await chatRunsApi.listEvents(conversationId, run.run_id)
        return {
          events: playback.events,
          mode: playback.events.length > 0 ? 'full' : 'none',
          lastEventId: playback.last_event_id ?? null,
        }
      } catch {
        return {
          events: [],
          mode: 'none',
          lastEventId: afterEventId ?? null,
        }
      }
    }

    if (afterEventId) {
      try {
        const playback = await chatRunsApi.listEvents(conversationId, run.run_id, { after_event_id: afterEventId })
        if (playback.anchor_found) {
          return {
            events: playback.events,
            mode: 'delta',
            lastEventId: playback.last_event_id ?? afterEventId ?? null,
          }
        }
      } catch {
        // Fall back to full playback recovery.
      }
    }

    return fetchFullPlayback()
  }, [])

  const reconcileCompletedRun = useCallback(async (
    conversationId: string,
    runId: string,
    sessionState: StreamingSession,
  ) => {
    if (terminalResolutionRunRef.current === runId) {
      return
    }
    terminalResolutionRunRef.current = runId
    if (!isActiveConversation(conversationId)) {
      return
    }
    persistChatRunSnapshot(conversationId, runId, sessionState)
    stopStreamingRun()
    const fetched = await fetchMessagesSafely(conversationId)
    if (!isActiveConversation(conversationId)) {
      return
    }
    if (!fetched) {
      return
    }
    clearChatRunSnapshot(conversationId)
    setSnapshotRunId(null)
    setSnapshotLastEventId(null)
    stopStreamingRun({ clearSession: true, clearSnapshotRunId: true })
  }, [fetchMessagesSafely, isActiveConversation, persistChatRunSnapshot, stopStreamingRun])

  const handleTerminalStreamError = useCallback(async (
    conversationId: string,
    runId: string,
    fallbackMessage: string,
  ) => {
    if (terminalResolutionRunRef.current === runId) {
      return
    }

    try {
      const run = await chatRunsApi.get(conversationId, runId)
      const playback = await loadPlaybackEvents(
        conversationId,
        run,
        sseClient.getLastEventId() ?? null,
      )
      if (playback.lastEventId) {
        sseClient.setLastEventId(playback.lastEventId)
      }
      const restoredSession = await restoreSessionFromPlayback(
        resolvePendingUserMessage(
          run.query,
          streamingSessionRef.current.pendingUserMessage,
        ),
        run.runtime_state,
        playback.mode === 'full' ? null : streamingSessionRef.current,
        playback,
      )

      if (run.status === 'success') {
        await reconcileCompletedRun(conversationId, run.run_id, restoredSession)
        return
      }

      terminalResolutionRunRef.current = runId

      persistChatRunSnapshot(conversationId, run.run_id, restoredSession, playback.lastEventId)
      stopStreamingRun()

      if (run.runtime_state?.hitl?.pending) {
        toast.success('运行等待人工确认，已恢复到 HITL 状态')
        return
      }
      if (run.status === 'interrupted') {
        toast.success('回答已中断，过程已保留，可点击继续')
        return
      }
      if (run.status === 'failed') {
        toast.error(run.error_message || fallbackMessage || '本次回答失败，可点击继续')
        return
      }
      if (isActiveRunStatus(run.status)) {
        toast.error('连接中断，过程已保留，可点击继续恢复当前运行')
        return
      }
    } catch {
      terminalResolutionRunRef.current = runId
      persistChatRunSnapshot(conversationId, runId, streamingSessionRef.current)
      stopStreamingRun()
      toast.error('连接中断，过程已保留，可点击继续恢复')
      return
    }

    terminalResolutionRunRef.current = runId
    persistChatRunSnapshot(conversationId, runId, streamingSessionRef.current)
    stopStreamingRun()
    toast.error(fallbackMessage || '连接中断，请重试')
  }, [loadPlaybackEvents, persistChatRunSnapshot, reconcileCompletedRun, restoreSessionFromPlayback, stopStreamingRun])

  const connectToRun = useCallback((
    conversationId: string,
    runId: string,
    lastEventId?: string | null,
  ) => {
    sseClient.disconnect()

    sseClient.onOpen(() => undefined)

    sseClient.setReconnectGuard(async (guardConversationId, guardRunId) => {
      try {
        const run = await chatRunsApi.get(guardConversationId, guardRunId)
        const shouldReconnect = isActiveRunStatus(run.status) && !run.runtime_state?.hitl?.pending
        if (!shouldReconnect) {
          await handleTerminalStreamError(guardConversationId, guardRunId, '当前运行已结束')
        }
        return shouldReconnect
      } catch {
        return false
      }
    })

    sseClient.onEvent((event: SSEEvent) => {
      updateStreamingSession((current) => applyStreamingEvent(current, event))

      switch (event.event_type) {
        case 'done': {
          stopStreamingRun()
          const completedSession = streamingSessionRef.current
          void reconcileCompletedRun(conversationId, runId, completedSession)
          break
        }
        case 'error': {
          stopStreamingRun()
          void handleTerminalStreamError(
            conversationId,
            runId,
            event.trace_data?.error_message || '处理请求时出现错误',
          )
          break
        }
        case 'hitl_requested': {
          persistChatRunSnapshot(conversationId, runId, streamingSessionRef.current)
          stopStreamingRun()
          break
        }
        default:
          break
      }
    })

    sseClient.onError(() => {
      void handleTerminalStreamError(conversationId, runId, '连接中断，请重试')
    })

    sseClient.connect(conversationId, runId, lastEventId)
  }, [
    handleTerminalStreamError,
    persistChatRunSnapshot,
    reconcileCompletedRun,
    stopStreamingRun,
    updateStreamingSession,
  ])

  const startStreamForRun = useCallback((
    conversationId: string,
    runId: string,
    sessionState: StreamingSession,
    lastEventId?: string | null,
  ) => {
    stopPlaybackReplay()
    terminalResolutionRunRef.current = null
    const nextSession = restoreStreamingSessionFromRun(
      sessionState.pendingUserMessage,
      undefined,
      sessionState,
    )
    replaceStreamingSession(nextSession)
    setCurrentRunId(runId)
    setIsRunning(true)
    persistChatRunSnapshot(conversationId, runId, nextSession, lastEventId)
    connectToRun(conversationId, runId, lastEventId)
  }, [connectToRun, persistChatRunSnapshot, replaceStreamingSession, setCurrentRunId, setIsRunning, stopPlaybackReplay])

  const resumeChatRun = useCallback(async (
    conversationId: string,
    run: ChatRunStatusResponse,
    snapshotSession: StreamingSession | null,
    snapshotLastEventId?: string | null,
  ) => {
    const fallbackUserMessage = resolvePendingUserMessage(
      run.query,
      snapshotSession?.pendingUserMessage,
    )
    const playback = await loadPlaybackEvents(conversationId, run, snapshotLastEventId)
    if (playback.lastEventId) {
      sseClient.setLastEventId(playback.lastEventId)
    }

    const restoredSession = await restoreSessionFromPlayback(
      fallbackUserMessage,
      run.runtime_state,
      playback.mode === 'full' ? null : snapshotSession,
      playback,
    )
    persistChatRunSnapshot(
      conversationId,
      run.run_id,
      restoredSession,
      playback.lastEventId ?? snapshotLastEventId,
    )

    if (!isActiveRunStatus(run.status)) {
      if (run.status === 'success') {
        await reconcileCompletedRun(conversationId, run.run_id, restoredSession)
        return
      }
      stopStreamingRun()
      return
    }

    if (run.runtime_state?.hitl?.pending) {
      stopStreamingRun()
      return
    }

    startStreamForRun(
      conversationId,
      run.run_id,
      restoredSession,
      playback.lastEventId ?? snapshotLastEventId,
    )
  }, [
    loadPlaybackEvents,
    persistChatRunSnapshot,
    reconcileCompletedRun,
    restoreSessionFromPlayback,
    startStreamForRun,
    stopStreamingRun,
  ])

  useEffect(() => {
    let cancelled = false
    activeConversationIdRef.current = id && id !== '' ? id : null

    sseClient.disconnect()
    if (!id || id === '') {
      clearChat()
    }
    setSnapshotRunId(null)
    setSnapshotLastEventId(null)
    terminalResolutionRunRef.current = null
    resetStreamingSession()

    const initialize = async () => {
      if (!id || id === '') return

      await fetchMessagesSafely(id)

      if (cancelled || !isActiveConversation(id)) return

      const snapshot = loadChatRunSnapshot(id)
      if (!snapshot) return

      if (!snapshot.runId) {
        setSnapshotRunId(null)
        setSnapshotLastEventId(snapshot.lastEventId ?? null)
        replaceStreamingSession(snapshot.session)
        return
      }

      try {
        const run = await chatRunsApi.get(id, snapshot.runId)
        if (cancelled || !isActiveConversation(id)) return
        await resumeChatRun(id, run, snapshot.session, snapshot.lastEventId)
      } catch {
        clearChatRunSnapshot(id)
        setSnapshotRunId(null)
        setSnapshotLastEventId(null)
        resetStreamingSession()
      }
    }

    void initialize()

    return () => {
      cancelled = true
      stopPlaybackReplay()
      sseClient.setReconnectGuard(undefined)
      sseClient.disconnect()
    }
  }, [clearChat, fetchMessagesSafely, id, isActiveConversation, replaceStreamingSession, resetStreamingSession, resumeChatRun, stopPlaybackReplay])

  useEffect(() => {
    if (!autoScrollRef.current) return
    scrollToMessageBottom(isRunning || isReplaying ? 'auto' : 'smooth')
  }, [isReplaying, isRunning, messages, scrollToMessageBottom, streamingSession.assistantContent, streamingSession.executionTrace, streamingSession.hitl])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [input])

  useEffect(() => {
    if (!id || id === '') return

    const hasSnapshotPayload = Boolean(
      snapshotRunId ||
      currentRunId ||
      isRunning ||
      streamingSession.pendingUserMessage ||
      streamingSession.executionTrace.length > 0 ||
      streamingSession.assistantContent ||
      streamingSession.finalAnswer ||
      streamingSession.hitl?.pending
    )

    if (!hasSnapshotPayload) return

    if (snapshotPersistTimerRef.current) {
      window.clearTimeout(snapshotPersistTimerRef.current)
    }

    snapshotPersistTimerRef.current = window.setTimeout(() => {
      saveChatRunSnapshot({
        conversationId: id,
        runId: snapshotRunId ?? currentRunId,
        lastEventId: sseClient.getLastEventId() ?? null,
        session: streamingSessionRef.current,
      })
      snapshotPersistTimerRef.current = null
    }, isRunning || isReplaying ? 150 : 0)

    return () => {
      if (snapshotPersistTimerRef.current) {
        window.clearTimeout(snapshotPersistTimerRef.current)
        snapshotPersistTimerRef.current = null
      }
    }
  }, [currentRunId, id, isReplaying, isRunning, snapshotRunId, streamingSession])

  const handleSendMessage = async () => {
    if (!input.trim() || isRunning || isReplaying) return

    const query = input.trim()
    stopPlaybackReplay()
    setInput('')
    setHitlInput('')
    if (!id || id === '') {
      clearChat()
    }
    setSnapshotRunId(null)
    setSnapshotLastEventId(null)
    sseClient.resetLastEventId()

    let conversationId = id
    if (!conversationId || conversationId === '') {
      try {
        const conversation = await createConversation(query.slice(0, 30))
        conversationId = conversation.id
        navigate(`/${conversationId}`)
      } catch {
        toast.error('创建会话失败')
        return
      }
    }

    const pendingUserMessage = buildPendingUserMessage(query)
    autoScrollRef.current = true
    setShowJumpToBottom(false)
    addMessage({
      id: pendingUserMessage.id,
      conversation_id: conversationId,
      role: 'user',
      content: query,
      created_at: pendingUserMessage.created_at,
    })
    const nextSession = createStreamingSessionState(pendingUserMessage)
    replaceStreamingSession(nextSession)
    persistChatRunSnapshot(conversationId, null, nextSession)

    try {
      const run = await chatRunsApi.create(conversationId, { query })
      startStreamForRun(conversationId, run.run_id, nextSession)
    } catch {
      clearChatRunSnapshot(conversationId)
      setSnapshotRunId(null)
      setSnapshotLastEventId(null)
      stopStreamingRun({ clearSession: true, clearSnapshotRunId: true })
      toast.error('发送消息失败')
    }
  }

  const handleInterrupt = async () => {
    if (!currentRunId || !id) return

    try {
      await chatRunsApi.interrupt(id, currentRunId)
      persistChatRunSnapshot(id, currentRunId, streamingSessionRef.current)
      stopStreamingRun()
      toast.success('已中断当前回答，过程已保留，可点击继续')
    } catch {
      toast.error('中断失败')
    }
  }

  const handleRetry = async () => {
    if (!id || isRunning || isReplaying) return

    const sourceRunId = snapshotRunId ?? loadChatRunSnapshot(id)?.runId ?? null
    if (sourceRunId) {
      try {
        const sourceRun = await chatRunsApi.get(id, sourceRunId)
        const pendingUserMessage = resolvePendingUserMessage(
          sourceRun.query,
          streamingSessionRef.current.pendingUserMessage,
        )

        if (isActiveRunStatus(sourceRun.status)) {
          const playback = await loadPlaybackEvents(id, sourceRun, snapshotLastEventId)
          if (playback.lastEventId) {
            sseClient.setLastEventId(playback.lastEventId)
          }
          const restoredSession = restoreStreamingSessionFromRun(
            pendingUserMessage,
            sourceRun.runtime_state,
            playback.mode === 'full' ? null : streamingSessionRef.current,
            playback.events,
          )
          replaceStreamingSession(restoredSession)

          if (sourceRun.runtime_state?.hitl?.pending) {
            stopStreamingRun()
            toast.success('当前运行等待人工确认，请先提交 HITL 决策')
            return
          }

          startStreamForRun(
            id,
            sourceRun.run_id,
            restoredSession,
            playback.lastEventId ?? snapshotLastEventId,
          )
          toast.success('已恢复当前运行')
          return
        }

        if (
          sourceRun.status === 'failed' ||
          sourceRun.status === 'interrupted' ||
          sourceRun.status === 'success'
        ) {
          const nextSession = createStreamingSessionState(pendingUserMessage)
          replaceStreamingSession(nextSession)
          const nextRun =
            sourceRun.status === 'failed' || sourceRun.status === 'interrupted'
              ? await chatRunsApi.retry(id, sourceRunId)
              : await chatRunsApi.regenerate(id, sourceRunId)
          startStreamForRun(id, nextRun.run_id, nextSession)
          return
        }
      } catch {
        // Fall through to message-backed regenerate / input retry.
      }
    }

    const lastAssistantMessage = [...messages].reverse().find((message) => (
      message.role === 'assistant' &&
      Boolean(message.run_id)
    ))
    if (lastAssistantMessage?.run_id) {
      const started = await handleRegenerate(lastAssistantMessage)
      if (started) {
        return
      }
    }

    const lastUserMessage = [...messages].reverse().find((message) => message.role === 'user')
    if (!lastUserMessage) return
    setInput(lastUserMessage.content)
  }

  const resolveSeedMessageForAssistant = useCallback((assistantMessage: Message): PendingUserMessage | null => {
    const pairedUserMessage = assistantMessage.reply_to_message_id
      ? messages.find((message) => message.id === assistantMessage.reply_to_message_id)
      : [...messages]
        .slice(0, Math.max(0, messages.findIndex((message) => message.id === assistantMessage.id)))
        .reverse()
        .find((message) => message.role === 'user')

    return resolvePendingUserMessage(
      pairedUserMessage?.content || '',
    )
  }, [messages])

  const handleRegenerate = useCallback(async (assistantMessage: Message): Promise<boolean> => {
    if (!id || isRunning || isReplaying || !assistantMessage.run_id) return false

    const pendingUserMessage = resolveSeedMessageForAssistant(assistantMessage)
    if (!pendingUserMessage) {
      toast.error('缺少可用于重新生成的原始问题')
      return false
    }

    try {
      const nextSession = createStreamingSessionState(pendingUserMessage)
      replaceStreamingSession(nextSession)
      const nextRun = await chatRunsApi.regenerate(id, assistantMessage.run_id)
      startStreamForRun(id, nextRun.run_id, nextSession)
      return true
    } catch {
      toast.error('重新生成失败')
      return false
    }
  }, [id, isReplaying, isRunning, replaceStreamingSession, resolveSeedMessageForAssistant, startStreamForRun])

  const submitHitlDecision = useCallback(async (type: HitlDecisionType) => {
    if (!id || !snapshotRunId || submittingHitl) return

    const requiresText = type === 'respond' || type === 'edit'
    if (requiresText && !hitlInput.trim()) {
      toast.error('请先输入需要提交的内容')
      return
    }

    const decisionValue = requiresText ? hitlInput.trim() : null

    setSubmittingHitl(true)
    try {
      await chatRunsApi.resume(id, snapshotRunId, {
        decision: {
          type,
          value: decisionValue,
        },
      })

      setHitlInput('')
      const run = await chatRunsApi.get(id, snapshotRunId)
      const restoredSession = restoreStreamingSessionFromRun(
        resolvePendingUserMessage(run.query, streamingSessionRef.current.pendingUserMessage),
        run.runtime_state,
        streamingSessionRef.current,
      )
      replaceStreamingSession(restoredSession)
      persistChatRunSnapshot(id, snapshotRunId, restoredSession)

      if (isActiveRunStatus(run.status) && !run.runtime_state?.hitl?.pending) {
        startStreamForRun(id, snapshotRunId, restoredSession, sseClient.getLastEventId())
      }

      toast.success('HITL 决策已提交')
    } catch {
      toast.error('提交 HITL 决策失败')
    } finally {
      setSubmittingHitl(false)
    }
  }, [hitlInput, id, persistChatRunSnapshot, replaceStreamingSession, snapshotRunId, startStreamForRun, submittingHitl])

  const hydratedMessages = useMemo(() => hydrateMessages(messages), [messages])

  const displayMessages = useMemo(
    () =>
      buildDisplayMessages(hydratedMessages, {
        isRunning,
        streamingContent: streamingSession.assistantContent,
        executionTrace: streamingSession.executionTrace,
        conversationId: id || '',
        pendingUserMessage: streamingSession.pendingUserMessage,
        session: streamingSession,
      }),
    [
      hydratedMessages,
      id,
      isRunning,
      streamingSession,
    ]
  )

  const composerStatusText = useMemo(() => {
    if (streamingSession.hitl?.pending) return '运行等待人工确认，请先提交 HITL 决策'
    if (isRunning) return '模型正在生成回答...'
    if (isReplaying) return '正在恢复执行过程...'
    if (snapshotRunId) return '已保留运行状态，可继续 / 重试 / 重新生成'
    return '支持 Markdown、表格与代码块'
  }, [isReplaying, isRunning, snapshotRunId, streamingSession.hitl?.pending])

  const hitlActions = streamingSession.hitl?.allowed_actions || []

  return (
    <div className="flex h-full bg-slate-100">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-slate-200/80 bg-white/80 px-4 py-3 backdrop-blur lg:px-6">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <Wand2 className="h-4 w-4 text-indigo-500" />
            AI 知识检索已启用
          </div>
        </div>

        {streamingSession.hitl?.pending && snapshotRunId && id && (
          <div className="border-b border-cyan-200 bg-cyan-50/80 px-4 py-3 text-xs text-cyan-900 lg:px-6">
            <div className="mx-auto flex max-w-4xl flex-col gap-3">
              <div>
                <p className="text-sm font-semibold">HITL 待处理</p>
                <p className="mt-1 whitespace-pre-wrap text-xs leading-6">
                  {streamingSession.hitl.prompt || '请补充必要信息后继续。'}
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
                    onClick={() => void submitHitlDecision('respond')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-cyan-200 bg-white px-3 py-1.5 text-xs font-medium text-cyan-700 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    提交回应
                  </button>
                )}
                {hitlActions.includes('approve') && (
                  <button
                    onClick={() => void submitHitlDecision('approve')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    通过
                  </button>
                )}
                {hitlActions.includes('edit') && (
                  <button
                    onClick={() => void submitHitlDecision('edit')}
                    disabled={submittingHitl}
                    className="rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    提交编辑
                  </button>
                )}
                {hitlActions.includes('reject') && (
                  <button
                    onClick={() => void submitHitlDecision('reject')}
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
              isRunning={isRunning || isReplaying}
              isReplaying={isReplaying}
              messagesEndRef={messagesEndRef}
              onRegenerate={handleRegenerate}
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
          isRunning={isRunning || isReplaying}
          hasMessages={messages.length > 0 || Boolean(streamingSession.pendingUserMessage)}
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

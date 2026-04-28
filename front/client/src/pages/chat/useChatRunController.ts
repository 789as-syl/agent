import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { toast } from 'sonner'

import { chatRunsApi, sseClient } from '../../api'
import type {
  ChatRunStatusResponse,
  Conversation,
  HitlDecisionType,
  Message,
  SSEEvent,
} from '../../types'
import { buildDisplayMessages, hydrateMessages } from './message-utils'
import {
  clearChatRunSnapshot,
  loadChatRunSnapshot,
  saveChatRunSnapshot,
} from './session-persistence'
import {
  buildPendingUserMessage,
  createChatRunControllerState,
  createClientMessageId,
  findHydratedAssistantMessage,
  hasRecoverableChatRun,
  isBusyChatRunPhase,
  reduceChatRunControllerState,
  resolveControllerPhaseFromRunStatus,
  resolvePendingUserMessage,
  shouldPersistChatRunSnapshot,
  toChatRunSnapshot,
  type ChatRunControllerState,
} from './chat-run-machine'
import {
  createStreamingSessionState,
  playbackStreamingEvents,
  restoreStreamingSessionFromRun,
  type PendingUserMessage,
  type StreamingSessionState,
} from './streaming-session'

const PLAYBACK_REPLAY_INTERVAL_MS = 16
const PLAYBACK_REPLAY_BATCH_SIZE = 4

interface PlaybackEventsLoadResult {
  events: SSEEvent[]
  mode: 'none' | 'full' | 'delta'
  lastEventId: string | null
}

interface UseChatRunControllerOptions {
  conversationId: string | null
  messages: Message[]
  fetchMessages: (conversationId: string) => Promise<void>
  createConversation: (title: string) => Promise<Conversation>
  navigateToConversation: (conversationId: string) => void
}

interface UseChatRunControllerResult {
  controller: ChatRunControllerState
  displayMessages: Message[]
  composerStatusText: string
  submittingHitl: boolean
  sendMessage: (input: string) => Promise<boolean>
  interruptRun: () => Promise<void>
  retryRun: () => Promise<void>
  regenerateFromMessage: (message: Message) => Promise<boolean>
  submitHitlDecision: (type: HitlDecisionType, value: string) => Promise<boolean>
}

export function useChatRunController({
  conversationId,
  messages,
  fetchMessages,
  createConversation,
  navigateToConversation,
}: UseChatRunControllerOptions): UseChatRunControllerResult {
  const [controller, dispatch] = useReducer(
    reduceChatRunControllerState,
    createChatRunControllerState(conversationId),
  )
  const [submittingHitl, setSubmittingHitl] = useState(false)

  const controllerRef = useRef(controller)
  const activeConversationIdRef = useRef<string | null>(conversationId)
  const replayTimerRef = useRef<number | null>(null)
  const replayResolverRef = useRef<((session: StreamingSessionState) => void) | null>(null)
  const finalizingFetchKeyRef = useRef<string | null>(null)
  const appliedEventIdsRef = useRef(new Set<string>())
  const appliedEventQueueRef = useRef<string[]>([])

  useEffect(() => {
    controllerRef.current = controller
  }, [controller])

  const rememberAppliedEventId = useCallback((eventId?: string | null) => {
    if (!eventId) return true
    if (appliedEventIdsRef.current.has(eventId)) {
      return false
    }
    appliedEventIdsRef.current.add(eventId)
    appliedEventQueueRef.current.push(eventId)
    if (appliedEventQueueRef.current.length > 1000) {
      const staleId = appliedEventQueueRef.current.shift()
      if (staleId) {
        appliedEventIdsRef.current.delete(staleId)
      }
    }
    return true
  }, [])

  const resetAppliedEventIds = useCallback(() => {
    appliedEventIdsRef.current.clear()
    appliedEventQueueRef.current = []
  }, [])

  const seedAppliedEventIds = useCallback((events: SSEEvent[]) => {
    events.forEach((event) => {
      rememberAppliedEventId(event.event_id)
    })
  }, [rememberAppliedEventId])

  const fetchMessagesSafely = useCallback(async (targetConversationId: string) => {
    try {
      await fetchMessages(targetConversationId)
      return true
    } catch {
      return false
    }
  }, [fetchMessages])

  const isActiveConversation = useCallback((targetConversationId: string) => {
    return activeConversationIdRef.current === targetConversationId
  }, [])

  const stopPlaybackReplay = useCallback(() => {
    if (replayTimerRef.current) {
      window.clearTimeout(replayTimerRef.current)
      replayTimerRef.current = null
    }
    if (replayResolverRef.current) {
      const resolve = replayResolverRef.current
      replayResolverRef.current = null
      resolve(controllerRef.current.session)
    }
  }, [])

  const replayPlaybackEventsIncrementally = useCallback((
    baseState: StreamingSessionState,
    events: SSEEvent[],
  ): Promise<StreamingSessionState> => {
    stopPlaybackReplay()
    dispatch({ type: 'replace_session', session: baseState })
    dispatch({ type: 'playback_started' })

    if (events.length === 0) {
      dispatch({ type: 'playback_finished', session: baseState })
      return Promise.resolve(baseState)
    }

    return new Promise((resolve) => {
      let eventIndex = 0
      let currentSession = baseState
      replayResolverRef.current = resolve

      const finishReplay = (finalSession: StreamingSessionState) => {
        const lastPlaybackEvent = events.length > 0 ? events[events.length - 1] : undefined
        if (replayTimerRef.current) {
          window.clearTimeout(replayTimerRef.current)
          replayTimerRef.current = null
        }
        replayResolverRef.current = null
        dispatch({
          type: 'playback_finished',
          session: finalSession,
          lastEventId: lastPlaybackEvent?.event_id ?? controllerRef.current.lastEventId,
        })
        resolve(finalSession)
      }

      const tick = () => {
        const batch = events.slice(eventIndex, eventIndex + PLAYBACK_REPLAY_BATCH_SIZE)
        if (batch.length === 0) {
          finishReplay(currentSession)
          return
        }

        currentSession = playbackStreamingEvents(currentSession, batch)
        seedAppliedEventIds(batch)
        dispatch({ type: 'replace_session', session: currentSession })
        const lastBatchEvent = batch.length > 0 ? batch[batch.length - 1] : undefined
        if (lastBatchEvent?.event_id) {
          dispatch({ type: 'sync_last_event_id', lastEventId: lastBatchEvent.event_id })
        }
        eventIndex += batch.length

        if (eventIndex >= events.length) {
          finishReplay(currentSession)
          return
        }

        replayTimerRef.current = window.setTimeout(tick, PLAYBACK_REPLAY_INTERVAL_MS)
      }

      tick()
    })
  }, [seedAppliedEventIds, stopPlaybackReplay])

  const loadPlaybackEvents = useCallback(async (
    targetConversationId: string,
    run: ChatRunStatusResponse,
    afterEventId?: string | null,
  ): Promise<PlaybackEventsLoadResult> => {
    const fetchFullPlayback = async (): Promise<PlaybackEventsLoadResult> => {
      try {
        const playback = await chatRunsApi.listEvents(targetConversationId, run.run_id)
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
        const playback = await chatRunsApi.listEvents(targetConversationId, run.run_id, { after_event_id: afterEventId })
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

  const restoreSessionFromPlayback = useCallback(async (
    fallbackUserMessage: PendingUserMessage | null,
    runtimeState: ChatRunStatusResponse['runtime_state'] | undefined,
    existingState: StreamingSessionState | null,
    playback: PlaybackEventsLoadResult,
  ): Promise<StreamingSessionState> => {
    if (playback.mode === 'full') {
      resetAppliedEventIds()
      const baseState = restoreStreamingSessionFromRun(
        fallbackUserMessage,
        runtimeState,
        null,
        [],
      )
      return replayPlaybackEventsIncrementally(baseState, playback.events)
    }

    const restored = restoreStreamingSessionFromRun(
      fallbackUserMessage,
      runtimeState,
      existingState ?? createStreamingSessionState(fallbackUserMessage),
      playback.events,
    )
    seedAppliedEventIds(playback.events)
    dispatch({
      type: 'playback_finished',
      session: restored,
      lastEventId: playback.lastEventId,
    })
    return restored
  }, [replayPlaybackEventsIncrementally, resetAppliedEventIds, seedAppliedEventIds])

  const resolveRunClientMessageId = useCallback((
    run: Pick<ChatRunStatusResponse, 'client_message_id' | 'runtime_state'>,
    fallback?: string | null,
  ) => {
    return run.client_message_id ?? run.runtime_state?.client_message_id ?? fallback ?? null
  }, [])

  const clearControllerSnapshot = useCallback((targetConversationId: string) => {
    clearChatRunSnapshot(targetConversationId)
  }, [])

  const resolveCompletedRun = useCallback(async (
    targetConversationId: string,
    run: ChatRunStatusResponse,
    restoredSession: StreamingSessionState,
    lastEventId: string | null,
  ) => {
    const clientMessageId = resolveRunClientMessageId(
      run,
      restoredSession.pendingUserMessage?.client_message_id ?? controllerRef.current.clientMessageId,
    )

    dispatch({
      type: 'restore_runtime',
      conversationId: targetConversationId,
      runId: run.run_id,
      clientMessageId,
      session: restoredSession,
      lastEventId,
      phase: 'finalizing',
      errorMessage: null,
    })

    const fetched = await fetchMessagesSafely(targetConversationId)
    if (!fetched && isActiveConversation(targetConversationId)) {
      toast.error('最终消息同步失败，过程已保留，可继续恢复')
    }
  }, [fetchMessagesSafely, isActiveConversation, resolveRunClientMessageId])

  const handleTerminalStreamError = useCallback(async (
    targetConversationId: string,
    runId: string,
    fallbackMessage: string,
  ) => {
    dispatch({ type: 'sse_reconnecting' })

    try {
      const run = await chatRunsApi.get(targetConversationId, runId)
      const playback = await loadPlaybackEvents(
        targetConversationId,
        run,
        controllerRef.current.lastEventId,
      )
      const clientMessageId = resolveRunClientMessageId(
        run,
        controllerRef.current.clientMessageId ?? controllerRef.current.session.pendingUserMessage?.client_message_id,
      )
      const restoredSession = await restoreSessionFromPlayback(
        resolvePendingUserMessage(
          run.query,
          clientMessageId,
          controllerRef.current.session.pendingUserMessage,
        ),
        run.runtime_state,
        playback.mode === 'full' ? null : controllerRef.current.session,
        playback,
      )

      if (!isActiveConversation(targetConversationId)) {
        return
      }

      if (run.status === 'success') {
        await resolveCompletedRun(
          targetConversationId,
          run,
          restoredSession,
          playback.lastEventId ?? controllerRef.current.lastEventId,
        )
        return
      }

      if (run.runtime_state?.hitl?.pending) {
        dispatch({
          type: 'restore_runtime',
          conversationId: targetConversationId,
          runId: run.run_id,
          clientMessageId,
          session: restoredSession,
          lastEventId: playback.lastEventId ?? controllerRef.current.lastEventId,
          phase: 'waiting_hitl',
        })
        toast.success('运行等待人工确认，已恢复到 HITL 状态')
        return
      }

      if (run.status === 'interrupted') {
        dispatch({
          type: 'restore_runtime',
          conversationId: targetConversationId,
          runId: run.run_id,
          clientMessageId,
          session: restoredSession,
          lastEventId: playback.lastEventId ?? controllerRef.current.lastEventId,
          phase: 'cancelled',
          errorMessage: run.error_message ?? null,
        })
        toast.success('回答已中断，过程已保留，可点击继续')
        return
      }

      if (run.status === 'failed') {
        dispatch({
          type: 'restore_runtime',
          conversationId: targetConversationId,
          runId: run.run_id,
          clientMessageId,
          session: restoredSession,
          lastEventId: playback.lastEventId ?? controllerRef.current.lastEventId,
          phase: 'failed',
          errorMessage: run.error_message || fallbackMessage,
        })
        toast.error(run.error_message || fallbackMessage || '本次回答失败，可点击继续')
        return
      }

      if (run.status === 'pending' || run.status === 'running') {
        dispatch({
          type: 'restore_runtime',
          conversationId: targetConversationId,
          runId: run.run_id,
          clientMessageId,
          session: restoredSession,
          lastEventId: playback.lastEventId ?? controllerRef.current.lastEventId,
          phase: 'reconnecting',
          errorMessage: fallbackMessage,
        })
        toast.error('连接中断，过程已保留，可点击继续恢复当前运行')
        return
      }
    } catch {
      if (isActiveConversation(targetConversationId)) {
        dispatch({
          type: 'restore_runtime',
          conversationId: targetConversationId,
          runId,
          clientMessageId: controllerRef.current.clientMessageId,
          session: controllerRef.current.session,
          lastEventId: controllerRef.current.lastEventId,
          phase: 'reconnecting',
          errorMessage: fallbackMessage,
        })
        toast.error('连接中断，过程已保留，可继续恢复')
      }
      return
    }

    if (isActiveConversation(targetConversationId)) {
      dispatch({ type: 'mark_failed', errorMessage: fallbackMessage || '连接中断，请重试' })
      toast.error(fallbackMessage || '连接中断，请重试')
    }
  }, [
    isActiveConversation,
    loadPlaybackEvents,
    resolveCompletedRun,
    resolveRunClientMessageId,
    restoreSessionFromPlayback,
  ])

  const connectToRun = useCallback((
    targetConversationId: string,
    runId: string,
    lastEventId?: string | null,
  ) => {
    sseClient.disconnect()

    sseClient.onOpen(() => {
      dispatch({ type: 'sse_open' })
    })

    sseClient.setReconnectGuard(async (guardConversationId, guardRunId) => {
      try {
        const run = await chatRunsApi.get(guardConversationId, guardRunId)
        const shouldReconnect = (run.status === 'pending' || run.status === 'running') && !run.runtime_state?.hitl?.pending
        if (!shouldReconnect) {
          await handleTerminalStreamError(guardConversationId, guardRunId, '当前运行已结束')
        } else {
          dispatch({ type: 'sse_reconnecting' })
        }
        return shouldReconnect
      } catch {
        return false
      }
    })

    sseClient.onEvent((event: SSEEvent) => {
      if (!rememberAppliedEventId(event.event_id)) {
        return
      }
      dispatch({ type: 'apply_event', event })

      switch (event.event_type) {
        case 'done': {
          sseClient.disconnect()
          void (async () => {
            const run = await chatRunsApi.get(targetConversationId, runId)
            if (!isActiveConversation(targetConversationId)) {
              return
            }
            await resolveCompletedRun(
              targetConversationId,
              run,
              controllerRef.current.session,
              event.event_id,
            )
          })()
          break
        }
        case 'error': {
          sseClient.disconnect()
          void handleTerminalStreamError(
            targetConversationId,
            runId,
            event.trace_data?.error_message || '处理请求时出现错误',
          )
          break
        }
        case 'hitl_requested': {
          sseClient.disconnect()
          dispatch({ type: 'mark_waiting_hitl' })
          break
        }
        default:
          break
      }
    })

    sseClient.onError(() => {
      sseClient.disconnect()
      void handleTerminalStreamError(targetConversationId, runId, '连接中断，请重试')
    })

    sseClient.connect(targetConversationId, runId, lastEventId)
  }, [handleTerminalStreamError, isActiveConversation, rememberAppliedEventId, resolveCompletedRun])

  const startStreamForRun = useCallback((
    targetConversationId: string,
    runId: string,
    clientMessageId: string | null,
    session: StreamingSessionState,
    lastEventId?: string | null,
  ) => {
    stopPlaybackReplay()
    dispatch({
      type: 'start_streaming',
      conversationId: targetConversationId,
      runId,
      clientMessageId,
      session: restoreStreamingSessionFromRun(
        session.pendingUserMessage,
        undefined,
        session,
      ),
      lastEventId: lastEventId ?? null,
    })
    connectToRun(targetConversationId, runId, lastEventId)
  }, [connectToRun, stopPlaybackReplay])

  const resumeChatRun = useCallback(async (
    targetConversationId: string,
    run: ChatRunStatusResponse,
    snapshotSession: StreamingSessionState | null,
    snapshotLastEventId?: string | null,
    snapshotClientMessageId?: string | null,
  ) => {
    const clientMessageId = resolveRunClientMessageId(
      run,
      snapshotClientMessageId ?? snapshotSession?.pendingUserMessage?.client_message_id,
    )
    const fallbackUserMessage = resolvePendingUserMessage(
      run.query,
      clientMessageId,
      snapshotSession?.pendingUserMessage,
    )
    const playback = await loadPlaybackEvents(targetConversationId, run, snapshotLastEventId)
    const restoredSession = await restoreSessionFromPlayback(
      fallbackUserMessage,
      run.runtime_state,
      playback.mode === 'full' ? null : snapshotSession,
      playback,
    )
    const lastEventId = playback.lastEventId ?? snapshotLastEventId ?? controllerRef.current.lastEventId

    if (!isActiveConversation(targetConversationId)) {
      return
    }

    if (run.status === 'success') {
      await resolveCompletedRun(targetConversationId, run, restoredSession, lastEventId)
      return
    }

    const phase = resolveControllerPhaseFromRunStatus(run, { preferReconnect: true })
    dispatch({
      type: 'restore_runtime',
      conversationId: targetConversationId,
      runId: run.run_id,
      clientMessageId,
      session: restoredSession,
      lastEventId,
      phase,
      errorMessage: run.error_message ?? null,
    })

    if (phase === 'streaming' || phase === 'reconnecting') {
      startStreamForRun(
        targetConversationId,
        run.run_id,
        clientMessageId,
        restoredSession,
        lastEventId,
      )
    }
  }, [
    isActiveConversation,
    loadPlaybackEvents,
    resolveCompletedRun,
    resolveRunClientMessageId,
    restoreSessionFromPlayback,
    startStreamForRun,
  ])

  const resolveSeedMessageForAssistant = useCallback((assistantMessage: Message): PendingUserMessage | null => {
    const pairedUserMessage = assistantMessage.reply_to_message_id
      ? messages.find((message) => message.id === assistantMessage.reply_to_message_id)
      : [...messages]
        .slice(0, Math.max(0, messages.findIndex((message) => message.id === assistantMessage.id)))
        .reverse()
        .find((message) => message.role === 'user')

    const nextClientMessageId = createClientMessageId()
    return resolvePendingUserMessage(
      pairedUserMessage?.content || '',
      nextClientMessageId,
    )
  }, [messages])

  const regenerateFromMessage = useCallback(async (assistantMessage: Message): Promise<boolean> => {
    if (!conversationId || isBusyChatRunPhase(controllerRef.current.phase) || controllerRef.current.isReplaying || !assistantMessage.run_id) {
      return false
    }

    const pendingUserMessage = resolveSeedMessageForAssistant(assistantMessage)
    if (!pendingUserMessage?.client_message_id) {
      toast.error('缺少可用于重新生成的原始问题')
      return false
    }

    dispatch({
      type: 'prepare_send',
      conversationId,
      clientMessageId: pendingUserMessage.client_message_id,
      pendingUserMessage,
    })

    try {
      const nextRun = await chatRunsApi.regenerate(conversationId, assistantMessage.run_id, {
        client_message_id: pendingUserMessage.client_message_id,
      })
      resetAppliedEventIds()
      startStreamForRun(
        conversationId,
        nextRun.run_id,
        pendingUserMessage.client_message_id,
        createStreamingSessionState(pendingUserMessage),
      )
      return true
    } catch {
      dispatch({ type: 'mark_failed', errorMessage: '重新生成失败' })
      toast.error('重新生成失败')
      return false
    }
  }, [conversationId, resetAppliedEventIds, resolveSeedMessageForAssistant, startStreamForRun])

  const retryRun = useCallback(async () => {
    if (!conversationId || isBusyChatRunPhase(controllerRef.current.phase) || controllerRef.current.isReplaying) return

    const sourceRunId = controllerRef.current.runId ?? loadChatRunSnapshot(conversationId)?.runId ?? null
    if (sourceRunId) {
      try {
        const sourceRun = await chatRunsApi.get(conversationId, sourceRunId)
        const sourceClientMessageId = resolveRunClientMessageId(
          sourceRun,
          controllerRef.current.clientMessageId ?? controllerRef.current.session.pendingUserMessage?.client_message_id,
        )
        const pendingUserMessage = resolvePendingUserMessage(
          sourceRun.query,
          sourceClientMessageId,
          controllerRef.current.session.pendingUserMessage,
        )

        if ((sourceRun.status === 'pending' || sourceRun.status === 'running') && !sourceRun.runtime_state?.hitl?.pending) {
          await resumeChatRun(
            conversationId,
            sourceRun,
            controllerRef.current.session,
            controllerRef.current.lastEventId,
            sourceClientMessageId,
          )
          toast.success('已恢复当前运行')
          return
        }

        if (sourceRun.runtime_state?.hitl?.pending) {
          dispatch({
            type: 'restore_runtime',
            conversationId,
            runId: sourceRun.run_id,
            clientMessageId: sourceClientMessageId,
            session: controllerRef.current.session,
            lastEventId: controllerRef.current.lastEventId,
            phase: 'waiting_hitl',
          })
          toast.success('当前运行等待人工确认，请先提交 HITL 决策')
          return
        }

        if (
          (sourceRun.status === 'failed' || sourceRun.status === 'interrupted' || sourceRun.status === 'success')
          && pendingUserMessage
        ) {
          const nextClientMessageId = createClientMessageId()
          const seededPendingUser = resolvePendingUserMessage(
            sourceRun.query,
            nextClientMessageId,
            pendingUserMessage,
          )
          if (!seededPendingUser?.client_message_id) {
            toast.error('缺少可恢复的用户问题')
            return
          }

          dispatch({
            type: 'prepare_send',
            conversationId,
            clientMessageId: seededPendingUser.client_message_id,
            pendingUserMessage: seededPendingUser,
          })

          const nextRun =
            sourceRun.status === 'failed' || sourceRun.status === 'interrupted'
              ? await chatRunsApi.retry(conversationId, sourceRunId, {
                client_message_id: seededPendingUser.client_message_id,
              })
              : await chatRunsApi.regenerate(conversationId, sourceRunId, {
                client_message_id: seededPendingUser.client_message_id,
              })

          resetAppliedEventIds()
          startStreamForRun(
            conversationId,
            nextRun.run_id,
            seededPendingUser.client_message_id,
            createStreamingSessionState(seededPendingUser),
          )
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
      const started = await regenerateFromMessage(lastAssistantMessage)
      if (started) {
        return
      }
    }

    const lastUserMessage = [...messages].reverse().find((message) => message.role === 'user')
    if (lastUserMessage) {
      toast.info(`可继续提问，最近一次问题：${lastUserMessage.content}`)
    }
  }, [conversationId, messages, regenerateFromMessage, resetAppliedEventIds, resolveRunClientMessageId, resumeChatRun, startStreamForRun])

  const sendMessage = useCallback(async (input: string) => {
    const normalized = input.trim()
    if (!normalized || isBusyChatRunPhase(controllerRef.current.phase) || controllerRef.current.isReplaying) return false

    stopPlaybackReplay()
    resetAppliedEventIds()

    let targetConversationId = conversationId
    if (!targetConversationId) {
      try {
        const conversation = await createConversation(normalized.slice(0, 30))
        targetConversationId = conversation.id
        navigateToConversation(conversation.id)
      } catch {
        toast.error('创建会话失败')
        return false
      }
    }

    const clientMessageId = createClientMessageId()
    const pendingUserMessage = buildPendingUserMessage(normalized, clientMessageId)

    dispatch({
      type: 'prepare_send',
      conversationId: targetConversationId,
      clientMessageId,
      pendingUserMessage,
    })

    try {
      const run = await chatRunsApi.create(targetConversationId, {
        query: normalized,
        client_message_id: clientMessageId,
      })
      startStreamForRun(
        targetConversationId,
        run.run_id,
        clientMessageId,
        createStreamingSessionState(pendingUserMessage),
      )
      return true
    } catch {
      dispatch({ type: 'mark_failed', errorMessage: '发送消息失败' })
      toast.error('发送消息失败')
      return false
    }
  }, [conversationId, createConversation, navigateToConversation, resetAppliedEventIds, startStreamForRun, stopPlaybackReplay])

  const interruptRun = useCallback(async () => {
    if (!conversationId || !controllerRef.current.runId) return

    try {
      await chatRunsApi.interrupt(conversationId, controllerRef.current.runId)
      sseClient.disconnect()
      dispatch({ type: 'mark_cancelled' })
      toast.success('已中断当前回答，过程已保留，可点击继续')
    } catch {
      toast.error('中断失败')
    }
  }, [conversationId])

  const submitHitlDecision = useCallback(async (type: HitlDecisionType, value: string) => {
    if (!conversationId || !controllerRef.current.runId || submittingHitl) return false

    const requiresText = type === 'respond' || type === 'edit'
    if (requiresText && !value.trim()) {
      toast.error('请先输入需要提交的内容')
      return false
    }

    setSubmittingHitl(true)
    try {
      await chatRunsApi.resume(conversationId, controllerRef.current.runId, {
        decision: {
          type,
          value: requiresText ? value.trim() : null,
        },
      })

      const run = await chatRunsApi.get(conversationId, controllerRef.current.runId)
      const clientMessageId = resolveRunClientMessageId(
        run,
        controllerRef.current.clientMessageId ?? controllerRef.current.session.pendingUserMessage?.client_message_id,
      )
      const restoredSession = restoreStreamingSessionFromRun(
        resolvePendingUserMessage(run.query, clientMessageId, controllerRef.current.session.pendingUserMessage),
        run.runtime_state,
        controllerRef.current.session,
      )

      dispatch({
        type: 'restore_runtime',
        conversationId,
        runId: run.run_id,
        clientMessageId,
        session: restoredSession,
        lastEventId: controllerRef.current.lastEventId,
        phase: resolveControllerPhaseFromRunStatus(run, { preferReconnect: false }),
      })

      if ((run.status === 'pending' || run.status === 'running') && !run.runtime_state?.hitl?.pending) {
        startStreamForRun(
          conversationId,
          run.run_id,
          clientMessageId,
          restoredSession,
          controllerRef.current.lastEventId,
        )
      }

      toast.success('HITL 决策已提交')
      return true
    } catch {
      toast.error('提交 HITL 决策失败')
      return false
    } finally {
      setSubmittingHitl(false)
    }
  }, [conversationId, resolveRunClientMessageId, startStreamForRun, submittingHitl])

  useEffect(() => {
    activeConversationIdRef.current = conversationId

    sseClient.setReconnectGuard(undefined)
    sseClient.disconnect()
    stopPlaybackReplay()
    dispatch({ type: 'reset', conversationId: conversationId ?? null })

    let cancelled = false
    const initialize = async () => {
      if (!conversationId) return

      await fetchMessagesSafely(conversationId)
      if (cancelled || !isActiveConversation(conversationId)) return

      const snapshot = loadChatRunSnapshot(conversationId)
      if (!snapshot) return

      if (!snapshot.runId) {
        dispatch({
          type: 'restore_runtime',
          conversationId,
          runId: null,
          clientMessageId: snapshot.client_message_id ?? snapshot.session.pendingUserMessage?.client_message_id ?? null,
          session: snapshot.session,
          lastEventId: snapshot.lastEventId ?? null,
          phase: snapshot.phase ?? 'cancelled',
          errorMessage: snapshot.errorMessage ?? null,
        })
        return
      }

      try {
        const run = await chatRunsApi.get(conversationId, snapshot.runId)
        if (cancelled || !isActiveConversation(conversationId)) return
        await resumeChatRun(
          conversationId,
          run,
          snapshot.session,
          snapshot.lastEventId,
          snapshot.client_message_id ?? snapshot.session.pendingUserMessage?.client_message_id ?? null,
        )
      } catch {
        clearControllerSnapshot(conversationId)
        dispatch({ type: 'reset', conversationId })
      }
    }

    void initialize()

    return () => {
      cancelled = true
      stopPlaybackReplay()
      sseClient.setReconnectGuard(undefined)
      sseClient.disconnect()
    }
  }, [
    clearControllerSnapshot,
    conversationId,
    fetchMessagesSafely,
    isActiveConversation,
    resumeChatRun,
    stopPlaybackReplay,
  ])

  useEffect(() => {
    const matchedAssistant = findHydratedAssistantMessage(messages, {
      conversationId: controller.conversationId,
      runId: controller.runId,
      clientMessageId: controller.clientMessageId,
    })
    if (controller.phase !== 'finalizing' || !matchedAssistant || !controller.conversationId) {
      return
    }
    clearControllerSnapshot(controller.conversationId)
    dispatch({ type: 'mark_completed' })
  }, [
    clearControllerSnapshot,
    controller.clientMessageId,
    controller.conversationId,
    controller.phase,
    controller.runId,
    messages,
  ])

  useEffect(() => {
    if (controller.phase !== 'finalizing' || !controller.conversationId || !controller.runId) {
      finalizingFetchKeyRef.current = null
      return
    }

    const key = `${controller.conversationId}:${controller.runId}:${controller.clientMessageId ?? ''}:${controller.lastEventId ?? ''}`
    if (finalizingFetchKeyRef.current === key) {
      return
    }
    finalizingFetchKeyRef.current = key
    void fetchMessagesSafely(controller.conversationId)
  }, [
    controller.clientMessageId,
    controller.conversationId,
    controller.lastEventId,
    controller.phase,
    controller.runId,
    fetchMessagesSafely,
  ])

  useEffect(() => {
    const snapshot = toChatRunSnapshot(controller)
    if (snapshot && shouldPersistChatRunSnapshot(controller)) {
      saveChatRunSnapshot(snapshot)
      return
    }
    if (controller.conversationId && (controller.phase === 'completed' || controller.phase === 'idle')) {
      clearControllerSnapshot(controller.conversationId)
    }
  }, [clearControllerSnapshot, controller])

  const hydratedMessages = useMemo(() => hydrateMessages(messages), [messages])

  const displayMessages = useMemo(() => {
    return buildDisplayMessages(hydratedMessages, {
      isRunning: isBusyChatRunPhase(controller.phase) || controller.isReplaying || controller.phase === 'waiting_hitl',
      streamingContent: controller.session.assistantContent,
      executionTrace: controller.session.executionTrace,
      conversationId: conversationId ?? controller.conversationId ?? '',
      activeRunId: controller.runId,
      activeClientMessageId: controller.clientMessageId,
      pendingUserMessage: controller.session.pendingUserMessage,
      session: controller.session,
    })
  }, [controller, conversationId, hydratedMessages])

  const composerStatusText = useMemo(() => {
    if (controller.session.hitl?.pending || controller.phase === 'waiting_hitl') {
      return '运行等待人工确认，请先提交 HITL 决策'
    }
    if (controller.phase === 'sending') return '正在发送问题...'
    if (controller.phase === 'streaming') return '模型正在生成回答...'
    if (controller.phase === 'finalizing') return '回答已生成，正在同步最终消息...'
    if (controller.phase === 'reconnecting') return '连接中断，过程已保留，可继续恢复当前运行'
    if (hasRecoverableChatRun(controller)) return '已保留运行状态，可继续 / 重试 / 重新生成'
    if (controller.isReplaying) return '正在恢复执行过程...'
    return '支持 Markdown、表格与代码块'
  }, [controller])

  return {
    controller,
    displayMessages,
    composerStatusText,
    submittingHitl,
    sendMessage,
    interruptRun,
    retryRun,
    regenerateFromMessage,
    submitHitlDecision,
  }
}

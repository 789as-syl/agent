import type { ChatRunStatusResponse, Message, SSEEvent } from '../../types'
import {
  applyStreamingEvent,
  createStreamingSessionState,
  type PendingUserMessage,
  type StreamingSessionState,
} from './streaming-session'

export type ChatRunPhase =
  | 'idle'
  | 'sending'
  | 'streaming'
  | 'waiting_hitl'
  | 'reconnecting'
  | 'finalizing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type ChatRunSseConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface ChatRunControllerState {
  conversationId: string | null
  runId: string | null
  clientMessageId: string | null
  phase: ChatRunPhase
  sseConnectionState: ChatRunSseConnectionState
  lastEventId: string | null
  session: StreamingSessionState
  isReplaying: boolean
  errorMessage: string | null
}

export interface ChatRunControllerSnapshot {
  conversationId: string
  runId: string | null
  phase?: ChatRunPhase
  client_message_id?: string | null
  lastEventId?: string | null
  session: StreamingSessionState
  errorMessage?: string | null
}

export type ChatRunControllerAction =
  | {
      type: 'prepare_send'
      conversationId: string
      clientMessageId: string
      pendingUserMessage: PendingUserMessage
    }
  | {
      type: 'start_streaming'
      conversationId: string
      runId: string
      clientMessageId: string | null
      session: StreamingSessionState
      lastEventId?: string | null
    }
  | {
      type: 'restore_runtime'
      conversationId: string
      runId: string | null
      clientMessageId: string | null
      session: StreamingSessionState
      lastEventId?: string | null
      phase: ChatRunPhase
      errorMessage?: string | null
    }
  | { type: 'playback_started' }
  | { type: 'playback_finished'; session: StreamingSessionState; lastEventId?: string | null }
  | { type: 'sse_open' }
  | { type: 'sse_reconnecting' }
  | { type: 'apply_event'; event: SSEEvent }
  | { type: 'mark_waiting_hitl'; errorMessage?: string | null }
  | { type: 'mark_failed'; errorMessage?: string | null }
  | { type: 'mark_cancelled'; errorMessage?: string | null }
  | { type: 'mark_completed' }
  | { type: 'sync_last_event_id'; lastEventId: string | null }
  | { type: 'replace_session'; session: StreamingSessionState }
  | { type: 'reset'; conversationId?: string | null }

export function createClientMessageId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `client-message-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function buildPendingUserMessage(content: string, clientMessageId: string): PendingUserMessage {
  return {
    id: `pending-user:${clientMessageId}`,
    client_message_id: clientMessageId,
    content,
    created_at: new Date().toISOString(),
  }
}

export function resolvePendingUserMessage(
  query: string | null | undefined,
  clientMessageId: string | null | undefined,
  existing?: PendingUserMessage | null,
): PendingUserMessage | null {
  if (existing) {
    if (clientMessageId && !existing.client_message_id) {
      return {
        ...existing,
        id: existing.id || `pending-user:${clientMessageId}`,
        client_message_id: clientMessageId,
      }
    }
    return existing
  }
  const normalized = query?.trim()
  if (!normalized) return null
  if (clientMessageId) {
    return buildPendingUserMessage(normalized, clientMessageId)
  }
  return {
    id: `pending-user:${Date.now()}`,
    content: normalized,
    created_at: new Date().toISOString(),
  }
}

export function createChatRunControllerState(
  conversationId: string | null = null,
): ChatRunControllerState {
  return {
    conversationId,
    runId: null,
    clientMessageId: null,
    phase: 'idle',
    sseConnectionState: 'idle',
    lastEventId: null,
    session: createStreamingSessionState(),
    isReplaying: false,
    errorMessage: null,
  }
}

export function reduceChatRunControllerState(
  state: ChatRunControllerState,
  action: ChatRunControllerAction,
): ChatRunControllerState {
  switch (action.type) {
    case 'prepare_send':
      return {
        conversationId: action.conversationId,
        runId: null,
        clientMessageId: action.clientMessageId,
        phase: 'sending',
        sseConnectionState: 'closed',
        lastEventId: null,
        session: createStreamingSessionState(action.pendingUserMessage),
        isReplaying: false,
        errorMessage: null,
      }

    case 'start_streaming':
      return {
        ...state,
        conversationId: action.conversationId,
        runId: action.runId,
        clientMessageId: action.clientMessageId,
        phase: 'streaming',
        sseConnectionState: 'connecting',
        lastEventId: action.lastEventId ?? state.lastEventId,
        session: action.session,
        isReplaying: false,
        errorMessage: null,
      }

    case 'restore_runtime':
      return {
        ...state,
        conversationId: action.conversationId,
        runId: action.runId,
        clientMessageId: action.clientMessageId,
        phase: action.phase,
        sseConnectionState: resolveConnectionStateForPhase(action.phase),
        lastEventId: action.lastEventId ?? null,
        session: action.session,
        isReplaying: false,
        errorMessage: action.errorMessage ?? null,
      }

    case 'playback_started':
      return {
        ...state,
        isReplaying: true,
      }

    case 'playback_finished':
      return {
        ...state,
        isReplaying: false,
        session: action.session,
        lastEventId: action.lastEventId ?? state.lastEventId,
      }

    case 'sse_open':
      return {
        ...state,
        sseConnectionState: 'open',
        phase: state.phase === 'reconnecting' || state.phase === 'sending' ? 'streaming' : state.phase,
      }

    case 'sse_reconnecting':
      return {
        ...state,
        phase: canReconnectFromPhase(state.phase) ? 'reconnecting' : state.phase,
        sseConnectionState: 'reconnecting',
      }

    case 'apply_event': {
      const session = applyStreamingEvent(state.session, action.event)
      const lastEventId = action.event.event_id || state.lastEventId

      if (action.event.event_type === 'done') {
        return {
          ...state,
          session,
          lastEventId,
          phase: 'finalizing',
          sseConnectionState: 'closed',
        }
      }

      if (action.event.event_type === 'hitl_requested') {
        return {
          ...state,
          session,
          lastEventId,
          phase: 'waiting_hitl',
          sseConnectionState: 'closed',
        }
      }

      if (action.event.event_type === 'error') {
        return {
          ...state,
          session,
          lastEventId,
          sseConnectionState: 'closed',
          errorMessage: action.event.trace_data?.error_message || state.errorMessage,
        }
      }

      return {
        ...state,
        session,
        lastEventId,
      }
    }

    case 'mark_waiting_hitl':
      return {
        ...state,
        phase: 'waiting_hitl',
        sseConnectionState: 'closed',
        errorMessage: action.errorMessage ?? null,
      }

    case 'mark_failed':
      return {
        ...state,
        phase: 'failed',
        sseConnectionState: 'closed',
        errorMessage: action.errorMessage ?? state.errorMessage,
      }

    case 'mark_cancelled':
      return {
        ...state,
        phase: 'cancelled',
        sseConnectionState: 'closed',
        errorMessage: action.errorMessage ?? state.errorMessage,
      }

    case 'mark_completed':
      return {
        ...createChatRunControllerState(state.conversationId),
        phase: 'completed',
      }

    case 'sync_last_event_id':
      return {
        ...state,
        lastEventId: action.lastEventId,
      }

    case 'replace_session':
      return {
        ...state,
        session: action.session,
      }

    case 'reset':
      return createChatRunControllerState(action.conversationId ?? null)

    default:
      return state
  }
}

export function isBusyChatRunPhase(phase: ChatRunPhase): boolean {
  return phase === 'sending' || phase === 'streaming' || phase === 'reconnecting' || phase === 'finalizing'
}

export function hasRecoverableChatRun(state: ChatRunControllerState): boolean {
  return Boolean(
    state.runId
    && (
      state.phase === 'streaming'
      || state.phase === 'waiting_hitl'
      || state.phase === 'reconnecting'
      || state.phase === 'finalizing'
      || state.phase === 'failed'
      || state.phase === 'cancelled'
    )
  )
}

export function shouldPersistChatRunSnapshot(state: ChatRunControllerState): boolean {
  if (!state.conversationId || state.phase === 'idle' || state.phase === 'completed') {
    return false
  }
  return Boolean(
    state.runId
    || state.clientMessageId
    || state.session.pendingUserMessage
    || state.session.executionTrace.length > 0
    || state.session.assistantContent
    || state.session.finalAnswer
    || state.session.hitl?.pending
  )
}

export function toChatRunSnapshot(state: ChatRunControllerState): ChatRunControllerSnapshot | null {
  if (!state.conversationId || !shouldPersistChatRunSnapshot(state)) {
    return null
  }
  return {
    conversationId: state.conversationId,
    runId: state.runId,
    phase: state.phase,
    client_message_id: state.clientMessageId,
    lastEventId: state.lastEventId,
    session: state.session,
    errorMessage: state.errorMessage,
  }
}

export function matchesStableAssociation(
  message: Pick<Message, 'client_message_id' | 'run_id' | 'role'>,
  params: {
    runId?: string | null
    clientMessageId?: string | null
    role?: Message['role']
  },
): boolean {
  if (params.role && message.role !== params.role) {
    return false
  }
  if (!params.runId || !params.clientMessageId) {
    return false
  }
  return message.run_id === params.runId && message.client_message_id === params.clientMessageId
}

export function findHydratedAssistantMessage(
  messages: Message[],
  params: {
    conversationId: string | null
    runId: string | null
    clientMessageId: string | null
  },
): Message | null {
  if (!params.conversationId || !params.runId || !params.clientMessageId) {
    return null
  }
  return (
    messages.find((message) => (
      message.conversation_id === params.conversationId
      && matchesStableAssociation(message, {
        runId: params.runId,
        clientMessageId: params.clientMessageId,
        role: 'assistant',
      })
    )) || null
  )
}

export function resolveControllerPhaseFromRunStatus(
  run: ChatRunStatusResponse,
  options: {
    preferReconnect?: boolean
  } = {},
): ChatRunPhase {
  if (run.runtime_state?.hitl?.pending) {
    return 'waiting_hitl'
  }
  if (run.status === 'success') {
    return 'finalizing'
  }
  if (run.status === 'failed') {
    return 'failed'
  }
  if (run.status === 'interrupted') {
    return 'cancelled'
  }
  if (run.status === 'pending' || run.status === 'running') {
    return options.preferReconnect ? 'reconnecting' : 'streaming'
  }
  return 'idle'
}

function canReconnectFromPhase(phase: ChatRunPhase): boolean {
  return phase === 'sending' || phase === 'streaming' || phase === 'reconnecting'
}

function resolveConnectionStateForPhase(phase: ChatRunPhase): ChatRunSseConnectionState {
  if (phase === 'streaming' || phase === 'sending') {
    return 'connecting'
  }
  if (phase === 'reconnecting') {
    return 'reconnecting'
  }
  if (phase === 'idle' || phase === 'completed') {
    return 'idle'
  }
  return 'closed'
}

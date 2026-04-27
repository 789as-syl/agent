import { sanitizeVisibleText } from './message-utils'
import type {
  ChatRunRuntimeState,
  ExecutionTraceEntry,
  HitlDecisionType,
  HitlRuntimeState,
  MessageContentBlock,
  SSEEvent,
  TraceEvidenceItem,
  TraceRange,
} from '../../types'

export interface PendingUserMessage {
  id: string
  content: string
  created_at: string
}

export interface StreamingSessionState {
  executionTrace: ExecutionTraceEntry[]
  contentBlocks: MessageContentBlock[] | null
  reasoningTruncated: boolean
  assistantContent: string
  finalAnswer: string
  pendingUserMessage: PendingUserMessage | null
  hitl: HitlRuntimeState | null
}

export function createStreamingSessionState(
  pendingUserMessage: PendingUserMessage | null = null
): StreamingSessionState {
  return {
    executionTrace: [],
    contentBlocks: null,
    reasoningTruncated: false,
    assistantContent: '',
    finalAnswer: '',
    pendingUserMessage,
    hitl: null,
  }
}

export function restoreStreamingSessionFromRun(
  fallbackUserMessage: PendingUserMessage | null,
  runtimeState?: ChatRunRuntimeState,
  existingState?: StreamingSessionState | null,
  playbackEvents?: SSEEvent[] | null,
): StreamingSessionState {
  const baseState = existingState ?? createStreamingSessionState(fallbackUserMessage)
  const nextPendingUserMessage = baseState.pendingUserMessage ?? fallbackUserMessage
  const playback = resolvePlaybackEvents(playbackEvents)
  const playbackState = playback.length > 0
    ? playbackStreamingEvents(
        {
          ...baseState,
          pendingUserMessage: nextPendingUserMessage,
        },
        playback,
      )
    : {
        ...baseState,
        pendingUserMessage: nextPendingUserMessage,
      }

  return {
    ...playbackState,
    pendingUserMessage: nextPendingUserMessage,
    hitl: resolveRuntimeHitl(runtimeState, playbackState.hitl),
  }
}

export function playbackStreamingEvents(
  state: StreamingSessionState,
  events: SSEEvent[],
): StreamingSessionState {
  return sortPlaybackEvents(events).reduce((current, event) => applyStreamingEvent(current, event), state)
}

export function applyStreamingEvent(
  state: StreamingSessionState,
  event: SSEEvent
): StreamingSessionState {
  switch (event.event_type) {
    case 'execution_trace':
      return upsertTraceEntry(state, buildExecutionTraceEntry(event))

    case 'generation_delta':
      return {
        ...state,
        assistantContent: sanitizeVisibleText(appendIncrementalText(
          state.assistantContent,
          event.trace_data?.delta,
          event.trace_data?.accumulated,
        )),
      }

    case 'reasoning_delta':
      return {
        ...state,
        reasoningTruncated: Boolean(event.trace_data?.truncated),
      }

    case 'final_answer': {
      const answer = sanitizeVisibleText(event.trace_data?.answer || '')
      return {
        ...state,
        assistantContent: answer,
        finalAnswer: answer,
        contentBlocks: normalizeContentBlocks(event.trace_data?.content_blocks),
        hitl: state.hitl ? { ...state.hitl, pending: false } : null,
      }
    }

    case 'hitl_requested': {
      const allowedActions = normalizeAllowedActions(event.trace_data?.allowed_actions)

      return {
        ...state,
        hitl: {
          pending: true,
          kind: event.trace_data?.kind || 'clarification',
          prompt: event.trace_data?.prompt || '请补充必要信息',
          allowed_actions: allowedActions,
        },
      }
    }

    case 'hitl_resolved':
      return {
        ...state,
        hitl: state.hitl
          ? {
              ...state.hitl,
              pending: false,
            }
          : null,
      }

    case 'error':
      return upsertTraceEntry(state, {
        id: event.event_id,
        kind: 'error',
        title: event.trace_data?.error_code || '运行错误',
        detail: event.trace_data?.error_message || '处理请求时发生错误',
        status: 'error',
        timestamp: Date.parse(event.timestamp) || Date.now(),
      })

    default:
      return state
  }
}

function resolvePlaybackEvents(
  explicitPlaybackEvents?: SSEEvent[] | null,
): SSEEvent[] {
  if (Array.isArray(explicitPlaybackEvents) && explicitPlaybackEvents.length > 0) {
    return sortPlaybackEvents(explicitPlaybackEvents.filter(isSSEEvent))
  }
  return []
}

export function sortPlaybackEvents(events: SSEEvent[]): SSEEvent[] {
  return [...events]
    .map((event, index) => ({ event, index }))
    .sort((left, right) => {
      if (left.event.step !== right.event.step) {
        return left.event.step - right.event.step
      }
      return left.index - right.index
    })
    .map(({ event }) => event)
}

function resolveRuntimeHitl(
  runtimeState: ChatRunRuntimeState | undefined,
  fallbackHitl: HitlRuntimeState | null,
): HitlRuntimeState | null {
  if (!runtimeState) {
    return fallbackHitl
  }

  const runtimeHitl = runtimeState.hitl
  const waitingForHitl = Boolean(runtimeHitl?.pending)

  if (!waitingForHitl) {
    return fallbackHitl
  }

  const allowedActions = normalizeAllowedActions(runtimeHitl?.allowed_actions)

  return {
    pending: waitingForHitl,
    kind: runtimeHitl?.kind || 'clarification',
    prompt: runtimeHitl?.prompt || fallbackHitl?.prompt || null,
    allowed_actions: allowedActions,
  }
}

function isSSEEvent(value: unknown): value is SSEEvent {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<SSEEvent>
  return (
    typeof candidate.event_id === 'string' &&
    typeof candidate.event_type === 'string' &&
    typeof candidate.step === 'number' &&
    typeof candidate.timestamp === 'string'
  )
}

function upsertTraceEntry(state: StreamingSessionState, payload: ExecutionTraceEntry): StreamingSessionState {
  const normalizedSemanticKey = normalizeSemanticKey(payload.semantic_key)
  const semanticMatchIndex = normalizedSemanticKey
    ? state.executionTrace.findIndex((step) => step.semantic_key === normalizedSemanticKey)
    : -1
  const existingIndex = semanticMatchIndex !== -1
    ? semanticMatchIndex
    : state.executionTrace.findIndex((step) => step.id === payload.id)

  if (existingIndex === -1) {
    return {
      ...state,
      executionTrace: [
        ...state.executionTrace,
        {
          ...payload,
          semantic_key: normalizedSemanticKey,
        },
      ],
    }
  }

  const executionTrace = [...state.executionTrace]
  executionTrace[existingIndex] = {
    ...payload,
    semantic_key: normalizedSemanticKey,
  }
  return {
    ...state,
    executionTrace,
  }
}

export function buildExecutionTraceEntry(event: Extract<SSEEvent, { event_type: 'execution_trace' }>): ExecutionTraceEntry {
  const traceData = event.trace_data || {}

  return {
    id: event.event_id,
    semantic_key: normalizeSemanticKey((traceData as unknown as { semantic_key?: unknown }).semantic_key),
    kind: traceData.kind || 'execution',
    title: traceData.title || traceData.tool_name || '执行轨迹',
    detail: resolveExecutionTraceDetail(traceData),
    decision_code: typeof traceData.decision_code === 'string' ? traceData.decision_code : undefined,
    status: traceData.status || inferExecutionStatus(traceData.kind),
    timestamp: Date.parse(event.timestamp) || Date.now(),
    evidence: normalizeTraceEvidenceItems(traceData.evidence),
    reasoning_anchor: normalizeTraceRange(traceData.reasoning_anchor),
    result_summary: typeof traceData.result_summary === 'string' ? traceData.result_summary : undefined,
    metadata: traceData.metadata,
  }
}

function normalizeAllowedActions(value: unknown): HitlDecisionType[] {
  if (!Array.isArray(value)) {
    return ['respond']
  }

  const actions = value
    .filter((item): item is HitlDecisionType => (
      item === 'respond' || item === 'approve' || item === 'edit' || item === 'reject'
    ))

  return actions.length > 0 ? actions : ['respond']
}

function normalizeSemanticKey(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined
  }
  const normalized = value.trim()
  return normalized ? normalized : undefined
}

function normalizeToolInput(value: unknown): string | undefined {
  if (!value || typeof value !== 'object') {
    return undefined
  }

  const candidate = value as Record<string, unknown>
  for (const key of ['query', 'expression', 'prompt']) {
    const raw = candidate[key]
    if (typeof raw === 'string' && raw.trim()) {
      return raw
    }
  }

  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return undefined
  }
}

export function resolveExecutionTraceDetail(traceData: {
  detail?: unknown
  result_summary?: unknown
  tool_input?: unknown
  metadata?: unknown
} | null | undefined): string | undefined {
  if (!traceData) {
    return undefined
  }

  const directDetail = typeof traceData.detail === 'string' && traceData.detail.trim()
    ? traceData.detail
    : undefined
  if (directDetail) {
    return directDetail
  }

  const legacySummary = typeof traceData.result_summary === 'string' && traceData.result_summary.trim()
    ? traceData.result_summary
    : undefined
  if (legacySummary) {
    return legacySummary
  }

  const normalizedToolInput = normalizeToolInput(traceData.tool_input)
  if (normalizedToolInput) {
    return normalizedToolInput
  }

  if (traceData.metadata && typeof traceData.metadata === 'object') {
    const metadata = traceData.metadata as Record<string, unknown>
    return normalizeToolInput(metadata.tool_input)
  }

  return undefined
}

function normalizeTraceEvidenceItems(value: unknown): TraceEvidenceItem[] | undefined {
  if (!Array.isArray(value)) {
    return undefined
  }

  const evidence = value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map((item) => {
      const source = typeof item.source === 'string' && item.source.trim() ? item.source : 'unknown'
      const label = typeof item.label === 'string' && item.label.trim() ? item.label : '证据'
      const payload: TraceEvidenceItem = { source, label }
      if (typeof item.detail === 'string' && item.detail.trim()) {
        payload.detail = item.detail
      }
      if (typeof item.event_id === 'string' && item.event_id.trim()) {
        payload.event_id = item.event_id
      }
      const reasoningRange = normalizeTraceRange(item.reasoning_range)
      if (reasoningRange) {
        payload.reasoning_range = reasoningRange
      }
      return payload
    })

  return evidence.length > 0 ? evidence : undefined
}

function normalizeTraceRange(value: unknown): TraceRange | undefined {
  if (!value || typeof value !== 'object') {
    return undefined
  }
  const candidate = value as Record<string, unknown>
  const start = typeof candidate.start === 'number' ? candidate.start : Number(candidate.start)
  const end = typeof candidate.end === 'number' ? candidate.end : Number(candidate.end)
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) {
    return undefined
  }
  return { start, end }
}

function normalizeContentBlocks(value: unknown): MessageContentBlock[] | null {
  if (!Array.isArray(value)) {
    return null
  }

  const blocks = value.filter((item): item is MessageContentBlock => {
    if (!item || typeof item !== 'object') return false
    const candidate = item as Record<string, unknown>
    return typeof candidate.type === 'string'
  })

  return blocks.length > 0 ? blocks : null
}

function inferExecutionStatus(kind?: string): ExecutionTraceEntry['status'] {
  if (kind === 'tool_start' || kind === 'tool_progress' || kind === 'tool_call') {
    return 'running'
  }
  return 'completed'
}

function appendIncrementalText(
  current: string,
  delta: string | undefined,
  accumulated: string | undefined,
): string {
  if (typeof delta === 'string' && delta.length > 0) {
    return current + delta
  }
  if (!current && typeof accumulated === 'string' && accumulated.length > 0) {
    return accumulated
  }
  return current
}

import type { SSEEvent, SSEEventType } from '../types'

const API_BASE_URL = '/api/v1'
const PRIMARY_EVENT_TYPES: SSEEventType[] = [
  'execution_trace',
  'reasoning_delta',
  'generation_delta',
  'final_answer',
  'hitl_requested',
  'hitl_resolved',
  'done',
  'error',
]
const PLAYBACK_CURSOR_EVENT_TYPES = new Set<SSEEvent['event_type']>([
  'execution_trace',
  'reasoning_delta',
  'generation_delta',
  'final_answer',
  'hitl_requested',
  'hitl_resolved',
  'done',
  'error',
])
const TERMINAL_EVENT_TYPES = new Set<SSEEvent['event_type']>([
  'done',
  'error',
  'hitl_requested',
])

export interface SSEClientConfig {
  baseUrl?: string
  maxReconnectAttempts?: number
  reconnectDelay?: number
}

export type SSEEventCallback = (event: SSEEvent) => void
export type SSEErrorCallback = (error: Event) => void
export type SSEOpenCallback = () => void
export type SSEReconnectGuard = (conversationId: string, runId: string) => Promise<boolean>

export class SSEClient {
  private baseUrl: string
  private maxReconnectAttempts: number
  private reconnectDelay: number
  private eventSource?: EventSource
  private reconnectTimer?: number
  // Last persisted playback event returned by stream/events APIs.
  private lastEventId?: string
  private reconnectAttempts = 0
  private isManualClose = false
  private terminalEventReceived = false
  private processedEventIds = new Set<string>()
  private processedEventQueue: string[] = []
  private readonly maxProcessedEventIds = 1000
  private currentConversationId?: string
  private currentRunId?: string
  private onEventCallback?: SSEEventCallback
  private onErrorCallback?: SSEErrorCallback
  private onOpenCallback?: SSEOpenCallback
  private reconnectGuard?: SSEReconnectGuard

  constructor(config: SSEClientConfig = {}) {
    this.baseUrl = config.baseUrl || API_BASE_URL
    this.maxReconnectAttempts = config.maxReconnectAttempts || 5
    this.reconnectDelay = config.reconnectDelay || 1000
  }

  onEvent(callback: SSEEventCallback) {
    this.onEventCallback = callback
  }

  onError(callback: SSEErrorCallback) {
    this.onErrorCallback = callback
  }

  onOpen(callback: SSEOpenCallback) {
    this.onOpenCallback = callback
  }

  setReconnectGuard(guard?: SSEReconnectGuard) {
    this.reconnectGuard = guard
  }

  connect(conversationId: string, runId: string, lastEventId?: string | null) {
    this.disconnect()
    this.isManualClose = false
    this.terminalEventReceived = false
    this.reconnectAttempts = 0
    this.currentConversationId = conversationId
    this.currentRunId = runId
    this.lastEventId = lastEventId || undefined
    this.processedEventIds.clear()
    this.processedEventQueue = []
    this.createEventSource(conversationId, runId)
  }

  private createEventSource(conversationId: string, runId: string) {
    if (this.eventSource) {
      this.eventSource.close()
    }

    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = undefined
    }

    const url = new URL(`${this.baseUrl}/conversations/${conversationId}/runs/${runId}/stream`, window.location.origin)
    if (this.lastEventId) {
      url.searchParams.set('after_event_id', this.lastEventId)
    }
    this.eventSource = new EventSource(url.toString(), { withCredentials: true })

    this.eventSource.onopen = () => {
      this.reconnectAttempts = 0
      if (this.onOpenCallback) {
        this.onOpenCallback()
      }
    }

    const eventTypes = [...PRIMARY_EVENT_TYPES]

    eventTypes.forEach((eventType) => {
      this.eventSource!.addEventListener(eventType, (event: Event) => {
        const messageEvent = event as MessageEvent
        try {
          const normalized = normalizeSSEEvent(JSON.parse(messageEvent.data))
          if (!normalized) {
            return
          }
          if (normalized.event_id && PLAYBACK_CURSOR_EVENT_TYPES.has(normalized.event_type)) {
            this.lastEventId = normalized.event_id
          }
          if (normalized.event_id) {
            if (this.processedEventIds.has(normalized.event_id)) {
              return
            }
            this.processedEventIds.add(normalized.event_id)
            this.processedEventQueue.push(normalized.event_id)
            if (this.processedEventQueue.length > this.maxProcessedEventIds) {
              const staleId = this.processedEventQueue.shift()
              if (staleId) {
                this.processedEventIds.delete(staleId)
              }
            }
          }
          if (this.onEventCallback) {
            this.onEventCallback(normalized)
          }
          if (TERMINAL_EVENT_TYPES.has(normalized.event_type)) {
            this.terminalEventReceived = true
            this.closeCurrentStream()
          }
        } catch (error) {
          console.error(`Failed to parse SSE event [${eventType}]`, error)
        }
      })
    })

    this.eventSource.onerror = (error) => {
      if (this.isManualClose || this.terminalEventReceived) {
        return
      }

      const readyState = this.eventSource?.readyState
      if (readyState === EventSource.CONNECTING) {
        return
      }
      if (readyState === EventSource.CLOSED) {
        void this.handleReconnect(conversationId, runId, error)
        return
      }

      this.notifyError(error)
    }
  }

  private async handleReconnect(conversationId: string, runId: string, error: Event) {
    if (this.terminalEventReceived) {
      this.closeCurrentStream()
      return
    }

    if (this.reconnectGuard) {
      try {
        const shouldReconnect = await this.reconnectGuard(conversationId, runId)
        if (!shouldReconnect) {
          this.closeCurrentStream()
          this.notifyError(error)
          return
        }
      } catch {
        this.closeCurrentStream()
        this.notifyError(error)
        return
      }
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached')
      this.notifyError(error)
      return
    }

    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)

    this.reconnectTimer = window.setTimeout(() => {
      if (!this.isManualClose) {
        this.createEventSource(conversationId, runId)
      }
      this.reconnectTimer = undefined
    }, delay)
  }

  disconnect() {
    this.isManualClose = true
    this.terminalEventReceived = false
    this.processedEventIds.clear()
    this.processedEventQueue = []
    this.currentConversationId = undefined
    this.currentRunId = undefined
    this.closeCurrentStream()
  }

  private notifyError(error: Event) {
    if (this.onErrorCallback) {
      this.onErrorCallback(error)
    }
  }

  resetLastEventId() {
    this.lastEventId = undefined
  }

  getLastEventId() {
    return this.lastEventId
  }

  setLastEventId(eventId: string) {
    this.lastEventId = eventId
  }

  private closeCurrentStream() {
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = undefined
    }
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = undefined
    }
  }
}

function normalizeSSEEvent(value: unknown): SSEEvent | null {
  if (!isRecord(value)) return null

  const normalizedEventType = normalizeEventType(readString(value.event_type))
  if (!normalizedEventType) return null

  const eventId = readString(value.event_id)
  const requestId = readString(value.request_id)
  const conversationId = readString(value.conversation_id)
  const timestamp = readString(value.timestamp)
  const step = typeof value.step === 'number' ? value.step : Number(value.step)

  if (!eventId || !requestId || !conversationId || !timestamp || !Number.isFinite(step)) {
    return null
  }

  return {
    event_id: eventId,
    request_id: requestId,
    conversation_id: conversationId,
    event_type: normalizedEventType,
    step,
    timestamp,
    is_final: Boolean(value.is_final),
    trace_data: normalizeTraceData(normalizedEventType, value.trace_data),
  } as SSEEvent
}

function normalizeEventType(eventType: string | null): SSEEventType | null {
  if (!eventType) return null
  if ((PRIMARY_EVENT_TYPES as string[]).includes(eventType)) {
    return eventType as SSEEventType
  }
  return null
}

function normalizeTraceData(
  eventType: SSEEventType,
  rawTraceData: unknown,
): Record<string, unknown> {
  const trace = isRecord(rawTraceData) ? rawTraceData : {}

  switch (eventType) {
    case 'hitl_requested':
      return {
        kind: readString(trace.kind) || 'clarification',
        prompt: readString(trace.prompt) || readString(trace.question) || '请补充必要信息',
        allowed_actions: normalizeAllowedActions(trace.allowed_actions),
      }

    case 'hitl_resolved':
      return {
        kind: readString(trace.kind) || 'clarification',
      }

    case 'execution_trace':
      return {
        kind: readString(trace.kind) || 'execution',
        title: readString(trace.title) || readString(trace.tool_name) || '执行轨迹',
        detail: readString(trace.detail) || readString(trace.result_summary),
        decision_code: readString(trace.decision_code) || undefined,
        status: readString(trace.status) || 'completed',
        tool_name: readString(trace.tool_name),
        tool_input: isRecord(trace.tool_input) ? trace.tool_input : undefined,
        result_summary: readString(trace.result_summary),
        result_count: typeof trace.result_count === 'number' ? trace.result_count : undefined,
        retrieval_failed: typeof trace.retrieval_failed === 'boolean' ? trace.retrieval_failed : undefined,
        evidence: normalizeTraceEvidence(trace.evidence),
        reasoning_anchor: normalizeTraceRange(trace.reasoning_anchor),
        metadata: isRecord(trace.metadata) ? trace.metadata : undefined,
      }

    case 'reasoning_delta':
      return {
        delta: readString(trace.delta) || '',
        accumulated: readString(trace.accumulated) || undefined,
        source: readString(trace.source) || undefined,
        truncated: typeof trace.truncated === 'boolean' ? trace.truncated : false,
      }

    default:
      return trace
  }
}

function normalizeAllowedActions(value: unknown): Array<'respond' | 'approve' | 'edit' | 'reject'> {
  if (!Array.isArray(value)) {
    return ['respond']
  }

  const actions = value
    .map((item) => (typeof item === 'string' ? item : null))
    .filter((item): item is 'respond' | 'approve' | 'edit' | 'reject' => (
      item === 'respond' || item === 'approve' || item === 'edit' || item === 'reject'
    ))

  return actions.length > 0 ? actions : ['respond']
}

function normalizeTraceEvidence(value: unknown): Array<Record<string, unknown>> | undefined {
  if (!Array.isArray(value)) {
    return undefined
  }

  const normalized = value
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => {
      const payload: Record<string, unknown> = {
        source: readString(item.source) || 'unknown',
        label: readString(item.label) || '证据',
      }
      const detail = readString(item.detail)
      if (detail) payload.detail = detail
      const eventId = readString(item.event_id)
      if (eventId) payload.event_id = eventId
      const reasoningRange = normalizeTraceRange(item.reasoning_range)
      if (reasoningRange) payload.reasoning_range = reasoningRange
      return payload
    })

  return normalized.length > 0 ? normalized : undefined
}

function normalizeTraceRange(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) {
    return undefined
  }
  const start = typeof value.start === 'number' ? value.start : Number(value.start)
  const end = typeof value.end === 'number' ? value.end : Number(value.end)
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) {
    return undefined
  }
  return { start, end }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

export const sseClient = new SSEClient()

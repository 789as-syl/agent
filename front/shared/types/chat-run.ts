import type { MessageContentBlock, TraceEvidenceItem, TraceRange } from './message'

export type HitlDecisionType = 'respond' | 'approve' | 'edit' | 'reject'

export interface ExecutionTraceData {
  kind: string
  title?: string
  detail?: string
  decision_code?: string
  status?: 'pending' | 'running' | 'completed' | 'error' | string
  tool_name?: string
  tool_input?: Record<string, unknown>
  result_summary?: string
  result_count?: number
  retrieval_failed?: boolean
  evidence?: TraceEvidenceItem[]
  reasoning_anchor?: TraceRange
  metadata?: Record<string, unknown>
}

export interface HitlRequestedData {
  kind: string
  prompt: string
  allowed_actions: HitlDecisionType[]
}

export interface HitlResolvedData {
  kind?: string
}

export interface GenerationDeltaData {
  delta: string
  accumulated?: string
}

export interface ReasoningDeltaData {
  delta: string
  accumulated?: string
  source?: string | null
  truncated?: boolean
}

export interface FinalAnswerData {
  answer: string
  content_blocks?: MessageContentBlock[]
}

export interface ErrorData {
  error_code: string
  error_message: string
  recoverable: boolean
}

export interface DoneData {
  total_steps: number
  duration_ms: number
  success: boolean
}

export type SSEEventType =
  | 'execution_trace'
  | 'reasoning_delta'
  | 'generation_delta'
  | 'final_answer'
  | 'hitl_requested'
  | 'hitl_resolved'
  | 'error'
  | 'done'

export interface SSEEventBase {
  event_id: string
  request_id: string
  conversation_id: string
  event_type: SSEEventType
  step: number
  timestamp: string
  is_final: boolean
}

export interface ExecutionTraceEvent extends SSEEventBase {
  event_type: 'execution_trace'
  trace_data: ExecutionTraceData
}

export interface GenerationDeltaEvent extends SSEEventBase {
  event_type: 'generation_delta'
  trace_data: GenerationDeltaData
}

export interface ReasoningDeltaEvent extends SSEEventBase {
  event_type: 'reasoning_delta'
  trace_data: ReasoningDeltaData
}

export interface FinalAnswerEvent extends SSEEventBase {
  event_type: 'final_answer'
  trace_data: FinalAnswerData
}

export interface HitlRequestedEvent extends SSEEventBase {
  event_type: 'hitl_requested'
  trace_data: HitlRequestedData
}

export interface HitlResolvedEvent extends SSEEventBase {
  event_type: 'hitl_resolved'
  trace_data: HitlResolvedData
}

export interface ErrorEvent extends SSEEventBase {
  event_type: 'error'
  trace_data: ErrorData
}

export interface DoneEvent extends SSEEventBase {
  event_type: 'done'
  trace_data: DoneData
}

export type SSEEvent =
  | ExecutionTraceEvent
  | ReasoningDeltaEvent
  | GenerationDeltaEvent
  | FinalAnswerEvent
  | HitlRequestedEvent
  | HitlResolvedEvent
  | ErrorEvent
  | DoneEvent

export interface CreateChatRunRequest {
  query: string
}

export interface ChatRun {
  run_id: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'interrupted'
}

export interface ChatRunMutationResponse {
  status: string
  run_id: string
  message?: string | null
}

export interface ResumeChatRunDecision {
  type: HitlDecisionType
  value: string | Record<string, unknown> | null
}

export interface ResumeChatRunRequest {
  decision: ResumeChatRunDecision
}

export interface HitlRuntimeState {
  pending: boolean
  kind?: string | null
  prompt?: string | null
  allowed_actions?: HitlDecisionType[]
}

export interface ChatRunRuntimeState {
  hitl?: HitlRuntimeState | null
}

export interface ChatRunStatusResponse extends ChatRun {
  query: string
  error_message?: string | null
  runtime_state: ChatRunRuntimeState
}

export interface ChatRunEventsResponse {
  after_event_id?: string | null
  anchor_found: boolean
  last_event_id?: string | null
  events: SSEEvent[]
}

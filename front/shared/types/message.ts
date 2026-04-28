export interface TraceRange {
  start: number
  end: number
}

export type AnswerBasis =
  | 'knowledge_backed'
  | 'direct'
  | 'retrieval_unavailable'
  | 'evidence_insufficient'
  | 'needs_clarification'

export interface TraceEvidenceItem {
  source: string
  label: string
  detail?: string
  event_id?: string
  reasoning_range?: TraceRange
  title?: string
  snippet?: string
  source_type?: string
  locator?: string
  evidence_type?: string
}

export interface MessageContentBlock {
  type: string
  text?: string
  [key: string]: unknown
}

export interface ExecutionTraceEntry {
  id: string
  semantic_key?: string
  kind: string
  title: string
  detail?: string
  decision_code?: string
  answer_basis?: AnswerBasis
  status: 'pending' | 'running' | 'completed' | 'error' | string
  timestamp: number
  evidence?: TraceEvidenceItem[]
  reasoning_anchor?: TraceRange
  result_summary?: string
  metadata?: Record<string, unknown>
}

export interface Message {
  id: string
  conversation_id: string
  run_id?: string | null
  client_message_id?: string | null
  role: 'user' | 'assistant'
  content: string
  content_blocks?: MessageContentBlock[] | null
  execution_trace?: ExecutionTraceEntry[] | null
  reply_to_message_id?: string | null
  created_at: string
}

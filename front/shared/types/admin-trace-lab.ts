export interface AdminTraceRunSummary {
  id: string
  conversation_id: string
  user_id: string
  query: string
  status: string
  parent_run_id?: string | null
  retry_of_run_id?: string | null
  event_count: number
  created_at: string
  updated_at: string
}

export interface AdminTraceRunListResponse {
  items: AdminTraceRunSummary[]
  total: number
  page: number
  page_size: number
}

export interface AdminTraceTimelineItem {
  event_id: string
  event_type: string
  step: number
  sequence_no?: number | null
  timestamp?: string | null
  title: string
  kind: string
  status: string
  detail_sanitized?: string | null
  metadata: Record<string, unknown>
  redacted: boolean
}

export interface AdminTraceRunDetailResponse {
  run: AdminTraceRunSummary
  events: AdminTraceTimelineItem[]
  after_event_id?: string | null
  anchor_found: boolean
  last_event_id?: string | null
  redaction_policy: string
}

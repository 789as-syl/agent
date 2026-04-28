export type MessageFeedbackRating = 'helpful' | 'not_helpful'
export type MessageFeedbackEvidenceQuality = 'sufficient' | 'insufficient' | 'missing'

export interface MessageFeedbackUpsertRequest {
  rating: MessageFeedbackRating
  evidence_quality?: MessageFeedbackEvidenceQuality | null
  hallucination_flag?: boolean
  comment?: string | null
}

export interface MessageFeedbackResponse {
  id: string
  user_id: string
  conversation_id: string
  message_id: string
  run_id?: string | null
  rating: MessageFeedbackRating
  evidence_quality?: MessageFeedbackEvidenceQuality | null
  hallucination_flag: boolean
  comment?: string | null
  created_at: string
  updated_at: string
}

export interface AdminMessageFeedbackItem {
  id: string
  user_id: string
  user_phone: string
  conversation_id: string
  message_id: string
  run_id?: string | null
  rating: MessageFeedbackRating
  evidence_quality?: MessageFeedbackEvidenceQuality | null
  hallucination_flag: boolean
  comment?: string | null
  message_preview: string
  created_at: string
  updated_at: string
}

export interface AdminMessageFeedbackListResponse {
  items: AdminMessageFeedbackItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminMessageFeedbackSummaryResponse {
  total_feedback: number
  helpful_count: number
  not_helpful_count: number
  hallucination_count: number
  evidence_missing_count: number
  evidence_insufficient_count: number
  comment_count: number
}

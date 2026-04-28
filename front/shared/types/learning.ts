export interface PracticeSessionCreate {
  title?: string | null
  question_ids?: string[]
  knowledge_point_id?: string | null
  limit?: number
}

export interface PracticeQuestionView {
  id: string
  question_text: string
  question_type: string
  options?: Array<{ label: string; text: string }> | null
  knowledge_point_ids: string[]
}

export interface PracticeSessionResponse {
  id: string
  title: string
  status: string
  source_type?: string | null
  source_id?: string | null
  question_ids: string[]
  current_index: number
  total_questions: number
  correct_count: number
  score: number
  completed_at?: string | null
  created_at: string
  updated_at: string
  questions: PracticeQuestionView[]
}

export interface PracticeSessionListResponse {
  items: PracticeSessionResponse[]
  total: number
  page: number
  page_size: number
}

export interface PracticeSubmitRequest {
  question_id: string
  answer: string
}

export interface PracticeAttemptResponse {
  id: string
  session_id: string
  question_id: string
  submitted_answer: string
  correct_answer?: string | null
  is_correct: boolean
  explanation?: string | null
  created_at: string
}

export interface PracticeSubmitResponse {
  attempt: PracticeAttemptResponse
  session: PracticeSessionResponse
  wrong_question_updated: boolean
  review_card_due_at?: string | null
}

export interface WrongQuestionResponse {
  id: string
  question_id: string
  question_text: string
  wrong_count: number
  last_answer?: string | null
  resolved_at?: string | null
  created_at: string
  updated_at: string
}

export interface WrongQuestionListResponse {
  items: WrongQuestionResponse[]
  total: number
  page: number
  page_size: number
}

export interface MasteryRecordResponse {
  id: string
  question_id?: string | null
  knowledge_point_id?: string | null
  mastery_score: number
  attempts_count: number
  correct_count: number
  last_practiced_at?: string | null
}

export interface MasteryRecordListResponse {
  items: MasteryRecordResponse[]
  total: number
}

export interface ReviewCardResponse {
  id: string
  question_id: string
  question_text: string
  status: string
  due_at: string
  interval_days: number
  ease_factor: number
  last_result?: string | null
}

export interface ReviewCardListResponse {
  items: ReviewCardResponse[]
  total: number
  page: number
  page_size: number
}

export interface LearningPathItemResponse {
  id: string
  knowledge_point_id?: string | null
  question_id?: string | null
  title: string
  status: string
  priority: number
  reason?: string | null
  created_at: string
  updated_at: string
}

export interface LearningPathResponse {
  items: LearningPathItemResponse[]
  total: number
}

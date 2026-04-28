export type QuestionType = 'single' | 'multiple' | 'true_false' | 'short_answer'

export interface QuestionOption {
  label: 'A' | 'B' | 'C' | 'D'
  text: string
}

export interface QuestionBankCreate {
  name: string
  description?: string
}

export interface QuestionBankUpdate {
  name?: string
  description?: string
}

export interface QuestionBankResponse {
  id: string
  name: string
  description: string | null
  total_questions: number
  created_at: string
  updated_at: string
}

export interface QuestionBankListResponse {
  items: QuestionBankResponse[]
  total: number
}

export interface QuestionCreate {
  bank_id: string
  external_id?: string
  question_text: string
  question_type: QuestionType
  options?: QuestionOption[] | null
  answer?: string
  explanation?: string
  knowledge_point_ids: string[]
}

export interface QuestionUpdate {
  question_text?: string
  question_type?: QuestionType
  options?: QuestionOption[] | null
  answer?: string
  explanation?: string
}

export interface QuestionImportItem {
  external_id?: string
  question_text: string
  question_type: QuestionType
  options?: QuestionOption[] | null
  answer: string
  explanation?: string
  knowledge_point_titles: string[]
}

export interface QuestionImportRequest {
  bank_id: string
  questions: QuestionImportItem[]
}

export interface QuestionVectorizeRequest {
  only_dirty?: boolean
  batch_size?: number
}

export interface QuestionKnowledgePointLink {
  knowledge_point_ids: string[]
}

export interface QuestionResponse {
  id: string
  bank_id: string
  external_id: string | null
  content_hash: string
  question_text: string
  question_type: QuestionType
  options: QuestionOption[] | null
  answer: string | null
  explanation: string | null
  knowledge_point_ids: string[]
  is_dirty: boolean
  created_at: string
  updated_at: string
}

export interface QuestionListResponse {
  items: QuestionResponse[]
  total: number
  page: number
  page_size: number
}

export interface QuestionImportResponse {
  total: number
  created: number
  updated: number
  skipped: number
  failed: number
  errors: string[]
}

export interface VectorizationJobResponse {
  id: string
  status: string
  progress: number
  total_questions: number
  processed_questions: number
  celery_task_id: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface VectorizationJobListResponse {
  items: VectorizationJobResponse[]
  total: number
  page: number
  page_size: number
}

export interface VectorizationJobStatusResponse {
  job_id: string
  status: string
  progress: number
  total_questions: number
  processed_questions: number
  remaining_questions: number
  error_message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface VectorizationJobRetryResponse {
  job_id: string
  new_job_id: string
  status: string
  message: string
}

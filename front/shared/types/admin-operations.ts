export type AdminTaskType = 'ingestion' | 'vectorization'

export interface AdminTaskConsoleItem {
  id: string
  task_type: AdminTaskType
  status: string
  progress: number
  title: string
  resource_id?: string | null
  celery_task_id?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

export interface AdminTaskConsoleResponse {
  items: AdminTaskConsoleItem[]
  total: number
  page: number
  page_size: number
  summary: Record<string, number>
}

export interface ContentQualityWarning {
  code: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  detail: string
  resource_type: string
  resource_id?: string | null
}

export interface QualityRadarResponse {
  document_count: number
  active_document_count: number
  chunk_count: number
  vectorized_chunk_count: number
  question_count: number
  vectorized_question_count: number
  dirty_question_count: number
  failed_ingestion_jobs: number
  failed_vectorization_jobs: number
  warnings: ContentQualityWarning[]
}

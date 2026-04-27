export interface IngestionJobResponse {
  id: string
  knowledge_point_id: string | null
  object_path: string
  file_type: string
  status: 'pending' | 'running' | 'success' | 'failed'
  progress: number
  error_message: string | null
  celery_task_id: string | null
  created_at: string
  updated_at: string
}

export interface IngestionJobRetryResponse {
  job_id: string
  new_job_id: string
  status: string
  message: string
}

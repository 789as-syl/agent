export interface PresignUploadRequest {
  file_name: string
  file_type: string
  file_size?: number
}

export interface PresignUploadResponse {
  upload_url: string
  object_path: string
  expires_in: number
}

export interface UploadCallbackRequest {
  object_path: string
  file_name: string
  file_type: string
  file_size: number
}

export interface UploadCallbackResponse {
  job_id: string
  status: string
  message: string
}

export interface KnowledgePointCreate {
  title: string
  file_type: string
}

export interface KnowledgePointUpdate {
  title?: string
}

export interface KnowledgePointChunkResponse {
  id: string
  chunk_index: number
  content: string
  metadata_json: Record<string, unknown>
  created_at: string
}

export interface KnowledgePointResponse {
  id: string
  title: string
  file_type: string
  object_path: string
  version: number
  is_active: boolean
  created_at: string
  updated_at: string
  chunks: KnowledgePointChunkResponse[]
}

export interface KnowledgePointListResponse {
  items: KnowledgePointResponse[]
  total: number
  page: number
  page_size: number
}

export interface KnowledgePointDeleteResponse {
  knowledge_point_id: string
  deleted_chunk_count: number
  detached_job_count: number
  revoked_task_count: number
  object_deleted: boolean
  message: string
}

export interface KnowledgePointDocumentUrlResponse {
  url: string
  preview_url?: string | null
  source_url?: string | null
  source_object_path?: string | null
  source_file_type?: string | null
  preview_object_path?: string | null
  preview_file_type?: string | null
  preview_available?: boolean | null
  preview_from_source?: boolean | null
  preview_status?: string | null
  preview_message?: string | null
  preview_error?: string | null
  preview_retrying?: boolean | null
  preview_metadata?: {
    status?: string | null
    message?: string | null
    error?: string | null
    retrying?: boolean | null
  } | null
  object_path: string
  file_type: string
  expires_in: number
}

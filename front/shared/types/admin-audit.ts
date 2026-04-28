export interface AdminAuditLogResponse {
  id: string
  actor_user_id: string
  action: string
  resource_type: string
  resource_id?: string | null
  summary: string
  metadata_json: Record<string, unknown>
  created_at: string
}

export interface AdminAuditLogListResponse {
  items: AdminAuditLogResponse[]
  total: number
  page: number
  page_size: number
}

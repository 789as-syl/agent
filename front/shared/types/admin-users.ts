export type AdminUserStatus = 'active' | 'disabled'

export interface AdminUser {
  id: string
  phone: string
  status: AdminUserStatus
  created_at: string
  status_changed_at: string | null
  status_changed_by_user_id: string | null
  ban_reason: string | null
}

export interface AdminUserListResponse {
  items: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface AdminUserStatusUpdateRequest {
  status: AdminUserStatus
  ban_reason?: string | null
}

export interface AdminConversationSummary {
  id: string
  user_id: string
  title: string
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface AdminConversationListResponse {
  items: AdminConversationSummary[]
  total: number
  page: number
  page_size: number
}

export interface AdminAuditPlaybackTrace {
  id: string
  kind: string
  title: string
  status: 'pending' | 'running' | 'completed' | 'error' | string
  timestamp: number
  detail_sanitized?: string | null
}

export interface AdminConversationAuditMessage {
  id: string
  conversation_id: string
  role: string
  content: string
  content_blocks?: Array<Record<string, unknown>> | null
  created_at: string
  audit_playback?: AdminAuditPlaybackTrace[] | null
  reply_to_message_id?: string | null
}

export interface AdminConversationMessageListResponse {
  items: AdminConversationAuditMessage[]
  total: number
  page: number
  page_size: number
}

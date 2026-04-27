import { apiClient } from './client'
import { createAdminUsersApi, type AdminUserQuery } from '@shared/api/module-factories'
import type {
  AdminConversationListResponse,
  AdminConversationMessageListResponse,
  AdminUser,
  AdminUserListResponse,
  AdminUserStatusUpdateRequest,
} from '../types'

const adminUsersApi = createAdminUsersApi<
  AdminUser,
  AdminUserListResponse,
  AdminUserStatusUpdateRequest,
  AdminConversationListResponse,
  AdminConversationMessageListResponse
>(apiClient)

export { adminUsersApi, type AdminUserQuery }

export const {
  getUsers,
  getUser,
  updateUserStatus,
  listUserConversations,
  listConversationMessages,
} = adminUsersApi

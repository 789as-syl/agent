import { apiClient } from './client'
import { createConversationsApi } from './module-factories'
import type {
  Conversation,
  CreateConversationRequest,
  UpdateConversationRequest,
  Message,
  PaginatedResponse,
} from '../types'

export const conversationsApi = createConversationsApi<
  Conversation,
  CreateConversationRequest,
  UpdateConversationRequest,
  PaginatedResponse<Conversation>,
  PaginatedResponse<Message>
>(apiClient)

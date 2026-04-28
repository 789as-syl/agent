import { apiClient } from './client'
import { createChatRunsApi } from '@shared/api/module-factories'
import type {
  ChatRun,
  ChatRunEventsResponse,
  ChatRunMutationResponse,
  ResumeChatRunRequest,
  ChatRunStatusResponse,
  CreateChatRunRequest,
  ChatRunRepeatRequest,
} from '../types'

const baseChatRunsApi = createChatRunsApi<
  CreateChatRunRequest,
  ChatRun,
  ChatRunStatusResponse,
  ChatRunMutationResponse,
  ResumeChatRunRequest,
  ChatRunEventsResponse
>(apiClient)

export const chatRunsApi = {
  ...baseChatRunsApi,
  retry: (conversationId: string, runId: string, data?: ChatRunRepeatRequest) =>
    apiClient.post<ChatRunMutationResponse>(`/conversations/${conversationId}/runs/${runId}/retry`, data),
  regenerate: (conversationId: string, runId: string, data?: ChatRunRepeatRequest) =>
    apiClient.post<ChatRunMutationResponse>(`/conversations/${conversationId}/runs/${runId}/regenerate`, data),
}

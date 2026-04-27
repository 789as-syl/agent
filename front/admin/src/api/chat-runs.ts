import { apiClient } from './client'
import { createChatRunsApi } from '@shared/api/module-factories'
import type {
  ChatRun,
  ChatRunEventsResponse,
  ChatRunMutationResponse,
  ChatRunStatusResponse,
  CreateChatRunRequest,
  ResumeChatRunRequest,
} from '../types'

export const chatRunsApi = createChatRunsApi<
  CreateChatRunRequest,
  ChatRun,
  ChatRunStatusResponse,
  ChatRunMutationResponse,
  ResumeChatRunRequest,
  ChatRunEventsResponse
>(apiClient)

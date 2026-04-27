import { apiClient } from './client'
import { createChatRunsApi } from '@shared/api/module-factories'
import type {
  ChatRun,
  ChatRunEventsResponse,
  ChatRunMutationResponse,
  ResumeChatRunRequest,
  ChatRunStatusResponse,
  CreateChatRunRequest,
} from '../types'

export const chatRunsApi = createChatRunsApi<
  CreateChatRunRequest,
  ChatRun,
  ChatRunStatusResponse,
  ChatRunMutationResponse,
  ResumeChatRunRequest,
  ChatRunEventsResponse
>(apiClient)

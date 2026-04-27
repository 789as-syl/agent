import { apiClient } from './client'
import { createChatRunsApi } from './module-factories'
import type { CreateChatRunRequest, ChatRun } from '../types'

export const chatRunsApi = createChatRunsApi<CreateChatRunRequest, ChatRun>(apiClient)

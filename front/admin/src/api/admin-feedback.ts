import { apiClient } from './client'
import { createMessageFeedbackApi } from '@shared/api/module-factories'
import type {
  AdminMessageFeedbackListResponse,
  AdminMessageFeedbackSummaryResponse,
  MessageFeedbackResponse,
  MessageFeedbackUpsertRequest,
} from '../types'

const adminFeedbackApi = createMessageFeedbackApi<
  MessageFeedbackUpsertRequest,
  MessageFeedbackResponse,
  AdminMessageFeedbackListResponse,
  AdminMessageFeedbackSummaryResponse
>(apiClient)

export const { listAdminFeedback, getAdminFeedbackSummary } = adminFeedbackApi

import { apiClient } from './client'
import { createMessageFeedbackApi } from '@shared/api/module-factories'
import type {
  AdminMessageFeedbackListResponse,
  AdminMessageFeedbackSummaryResponse,
  MessageFeedbackResponse,
  MessageFeedbackUpsertRequest,
} from '../types'

const feedbackApi = createMessageFeedbackApi<
  MessageFeedbackUpsertRequest,
  MessageFeedbackResponse,
  AdminMessageFeedbackListResponse,
  AdminMessageFeedbackSummaryResponse
>(apiClient)

export const { getMessageFeedback, upsertMessageFeedback } = feedbackApi

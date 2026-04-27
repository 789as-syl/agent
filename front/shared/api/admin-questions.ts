import { apiClient } from './client'
import { createAdminQuestionsApi, type QuestionQuery } from './module-factories'
import type {
  QuestionBankCreate,
  QuestionBankListResponse,
  QuestionBankResponse,
  QuestionBankUpdate,
  QuestionCreate,
  QuestionUpdate,
  QuestionListResponse,
  QuestionResponse,
  QuestionImportRequest,
  QuestionImportResponse,
  QuestionVectorizeRequest,
  VectorizationJobResponse,
  QuestionKnowledgePointLink,
} from '../types'

const adminQuestionsApi = createAdminQuestionsApi<
  QuestionBankCreate,
  QuestionBankListResponse,
  QuestionBankResponse,
  QuestionBankUpdate,
  QuestionCreate,
  QuestionUpdate,
  QuestionListResponse,
  QuestionResponse,
  QuestionImportRequest,
  QuestionImportResponse,
  QuestionVectorizeRequest,
  VectorizationJobResponse,
  QuestionKnowledgePointLink
>(apiClient)

export { adminQuestionsApi, type QuestionQuery }

export const {
  getQuestionBanks,
  createQuestionBank,
  updateQuestionBank,
  deleteQuestionBank,
  getQuestions,
  createQuestion,
  getQuestion,
  updateQuestion,
  deleteQuestion,
  importQuestions,
  getVectorizationJob,
  linkKnowledgePoints,
  unlinkKnowledgePoint,
} = adminQuestionsApi

export const vectorizeQuestions = (
  data: QuestionVectorizeRequest = { only_dirty: true, batch_size: 10 }
): Promise<VectorizationJobResponse> => adminQuestionsApi.vectorizeQuestions(data)

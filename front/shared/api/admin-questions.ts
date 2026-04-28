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
  VectorizationJobListResponse,
  VectorizationJobRetryResponse,
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
  VectorizationJobListResponse,
  VectorizationJobRetryResponse,
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
  listVectorizationJobs,
  getVectorizationJob,
  retryVectorizationJob,
  linkKnowledgePoints,
  unlinkKnowledgePoint,
} = adminQuestionsApi

export const vectorizeQuestions = (
  data: QuestionVectorizeRequest = { only_dirty: true, batch_size: 10 }
): Promise<VectorizationJobResponse> => adminQuestionsApi.vectorizeQuestions(data)

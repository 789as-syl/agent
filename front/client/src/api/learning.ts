import { apiClient } from './client'
import { createLearningApi } from '@shared/api/module-factories'
import type {
  LearningPathResponse,
  MasteryRecordListResponse,
  PracticeSessionCreate,
  PracticeSessionListResponse,
  PracticeSessionResponse,
  PracticeSubmitRequest,
  PracticeSubmitResponse,
  ReviewCardListResponse,
  WrongQuestionListResponse,
} from '../types'

const learningApi = createLearningApi<
  PracticeSessionCreate,
  PracticeSessionResponse,
  PracticeSessionListResponse,
  PracticeSubmitRequest,
  PracticeSubmitResponse,
  WrongQuestionListResponse,
  MasteryRecordListResponse,
  ReviewCardListResponse,
  LearningPathResponse
>(apiClient)

export const {
  createPracticeSession,
  listPracticeSessions,
  getPracticeSession,
  submitPracticeAnswer,
  listWrongQuestions,
  listMastery,
  listReviewCards,
  getLearningPath,
} = learningApi

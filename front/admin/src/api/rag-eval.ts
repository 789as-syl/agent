import { apiClient } from './client'
import { createRagEvalApi } from '@shared/api/module-factories'
import type {
  RagEvalRunCreate,
  RagEvalRunListResponse,
  RagEvalRunResponse,
  RagGoldenQueryCreate,
  RagGoldenQueryListResponse,
  RagGoldenQueryResponse,
} from '../types'

const ragEvalApi = createRagEvalApi<
  RagGoldenQueryCreate,
  RagGoldenQueryResponse,
  RagGoldenQueryListResponse,
  RagEvalRunCreate,
  RagEvalRunResponse,
  RagEvalRunListResponse
>(apiClient)

export const { listGoldenQueries, createGoldenQuery, deleteGoldenQuery, listEvalRuns, createEvalRun } = ragEvalApi

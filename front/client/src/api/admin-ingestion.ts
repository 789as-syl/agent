import { apiClient } from './client'
import { createAdminIngestionApi, type KnowledgePointQuery } from '@shared/api/module-factories'
import type {
  PresignUploadRequest,
  PresignUploadResponse,
  UploadCallbackRequest,
  UploadCallbackResponse,
  KnowledgePointCreate,
  KnowledgePointUpdate,
  KnowledgePointListResponse,
  KnowledgePointResponse,
  KnowledgePointDeleteResponse,
  KnowledgePointDocumentUrlResponse,
  IngestionJobResponse,
  IngestionJobListResponse,
  IngestionJobRetryResponse,
} from '../types'

const adminIngestionApi = createAdminIngestionApi<
  PresignUploadRequest,
  PresignUploadResponse,
  UploadCallbackRequest,
  UploadCallbackResponse,
  KnowledgePointCreate,
  KnowledgePointUpdate,
  KnowledgePointListResponse,
  KnowledgePointResponse,
  KnowledgePointDeleteResponse,
  KnowledgePointDocumentUrlResponse,
  IngestionJobResponse,
  IngestionJobListResponse,
  IngestionJobRetryResponse
>(apiClient)

export { adminIngestionApi, type KnowledgePointQuery }

export const {
  presignUpload,
  uploadCallback,
  getKnowledgePoints,
  createKnowledgePoint,
  getKnowledgePoint,
  getKnowledgePointDocumentUrl,
  updateKnowledgePoint,
  reindexKnowledgePoint,
  getIngestionJobs,
  getIngestionJob,
  retryIngestionJob,
} = adminIngestionApi

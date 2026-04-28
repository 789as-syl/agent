import { apiClient } from './client'
import { createAdminIngestionApi, type KnowledgePointQuery } from './module-factories'
import type {
  PresignUploadRequest,
  PresignUploadResponse,
  UploadCallbackRequest,
  UploadCallbackResponse,
  KnowledgePointCreate,
  KnowledgePointDeleteResponse,
  KnowledgePointUpdate,
  KnowledgePointListResponse,
  KnowledgePointResponse,
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
  deleteKnowledgePoint,
  getKnowledgePointDocumentUrl,
  updateKnowledgePoint,
  reindexKnowledgePoint,
  getIngestionJobs,
  getIngestionJob,
  retryIngestionJob,
} = adminIngestionApi

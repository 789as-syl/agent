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
  getIngestionJob,
  retryIngestionJob,
} = adminIngestionApi

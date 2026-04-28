import { apiClient } from './client'
import { createAdminIngestionApi, type KnowledgePointQuery } from '@shared/api/module-factories'
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

export type KnowledgePointPreviewState = 'ready' | 'not_ready' | 'retrying' | 'failed'

export interface KnowledgePointDocumentPreviewResolved {
  url: string
  state: KnowledgePointPreviewState | null
  stateMessage: string
}

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

const normalizePreviewState = (response: KnowledgePointDocumentUrlResponse): KnowledgePointPreviewState | null => {
  const rawStatus = response.preview_status ?? response.preview_metadata?.status ?? null
  const normalizedStatus = rawStatus?.trim().toLowerCase().replace(/[-\s]+/g, '_') ?? ''
  const retrying = response.preview_retrying ?? response.preview_metadata?.retrying ?? false

  if (normalizedStatus.includes('fail') || normalizedStatus.includes('error')) return 'failed'
  if (retrying || normalizedStatus.includes('retry')) return 'retrying'
  if (
    normalizedStatus === 'not_ready' ||
    normalizedStatus === 'pending' ||
    normalizedStatus === 'processing' ||
    normalizedStatus === 'queued'
  ) {
    return 'not_ready'
  }
  if (normalizedStatus === 'ready' || normalizedStatus === 'success' || normalizedStatus === 'available') {
    return 'ready'
  }
  return null
}

const resolvePreviewStateMessage = (
  state: KnowledgePointPreviewState | null,
  response: KnowledgePointDocumentUrlResponse
): string => {
  const explicitMessage =
    response.preview_message ??
    response.preview_error ??
    response.preview_metadata?.message ??
    response.preview_metadata?.error ??
    ''

  if (explicitMessage.trim()) return explicitMessage
  if (state === 'failed') return '预览生成失败，已回退到源文件地址。'
  if (state === 'retrying') return '预览尚未完成，系统正在重试，已回退到源文件地址。'
  if (state === 'not_ready') return '预览尚未就绪，已回退到源文件地址。'
  return ''
}

export const resolveKnowledgePointDocumentPreview = (
  response: KnowledgePointDocumentUrlResponse
): KnowledgePointDocumentPreviewResolved => {
  const previewUrl = response.preview_url?.trim() ?? ''
  const sourceUrl = response.source_url?.trim() ?? ''
  const legacyUrl = response.url?.trim() ?? ''
  const resolvedUrl = previewUrl || sourceUrl || legacyUrl
  const state = normalizePreviewState(response)
  const stateMessage = resolvePreviewStateMessage(state, response)

  return {
    url: resolvedUrl,
    state,
    stateMessage,
  }
}

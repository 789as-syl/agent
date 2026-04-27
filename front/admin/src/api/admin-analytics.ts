import type { AxiosRequestConfig } from 'axios'

import { apiClient } from './client'
import { createAdminAnalyticsApi } from '@shared/api/module-factories'
import type { AdminDashboardResponse, AdminRange, KnowledgeGraphResponse } from '../types'

const adminAnalyticsApi = createAdminAnalyticsApi<
  AdminDashboardResponse,
  AdminRange,
  KnowledgeGraphResponse,
  AxiosRequestConfig
>(apiClient)

export const getAdminDashboard = (range: AdminRange = '7d'): Promise<AdminDashboardResponse> =>
  adminAnalyticsApi.getAdminDashboard(range)

export const getKnowledgeGraph = (
  range: AdminRange = '7d',
  nodeLimit = 200,
  options?: {
    includeOrphanQuestions?: boolean
    forceRefresh?: boolean
    requestConfig?: AxiosRequestConfig
  }
): Promise<KnowledgeGraphResponse> => adminAnalyticsApi.getKnowledgeGraph(range, nodeLimit, options)

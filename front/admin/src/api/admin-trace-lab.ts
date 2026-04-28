import { apiClient } from './client'
import { createAdminTraceLabApi } from '@shared/api/module-factories'
import type { AdminTraceRunDetailResponse, AdminTraceRunListResponse } from '../types'

const adminTraceLabApi = createAdminTraceLabApi<AdminTraceRunListResponse, AdminTraceRunDetailResponse>(apiClient)

export const { listTraceRuns, getTraceRun } = adminTraceLabApi

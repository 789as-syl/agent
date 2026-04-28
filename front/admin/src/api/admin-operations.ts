import { apiClient } from './client'
import { createAdminOperationsApi } from '@shared/api/module-factories'
import type { AdminTaskConsoleResponse, QualityRadarResponse } from '../types'

const adminOperationsApi = createAdminOperationsApi<AdminTaskConsoleResponse, QualityRadarResponse>(apiClient)

export const { getTasks, getQualityRadar } = adminOperationsApi

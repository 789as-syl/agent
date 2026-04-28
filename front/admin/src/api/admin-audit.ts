import { apiClient } from './client'
import { createAdminAuditApi } from '@shared/api/module-factories'
import type { AdminAuditLogListResponse } from '../types'

const adminAuditApi = createAdminAuditApi<AdminAuditLogListResponse>(apiClient)

export const { listAuditLogs } = adminAuditApi

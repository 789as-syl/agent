import axios from 'axios'

import {
  createApiClientModule,
  type ApiClientConfig,
  type ApiErrorDetail,
  type ApiErrorResponse,
} from '@shared/api/client-core'

const moduleExports = createApiClientModule(axios)

export const apiClient = moduleExports.apiClient
export const extractApiErrorMessage = moduleExports.extractApiErrorMessage

export type { ApiClientConfig, ApiErrorDetail, ApiErrorResponse }

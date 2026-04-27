const API_BASE_URL = '/api/v1'

export interface ApiClientConfig {
  baseUrl?: string
}

export interface ApiErrorDetail {
  error_code: string
  message: string
  details: Record<string, unknown>
}

export interface ApiErrorResponse {
  detail: ApiErrorDetail
}

type RequestHeaders = Record<string, unknown>

type RequestConfig = {
  headers?: RequestHeaders
  data?: unknown
  url?: string
  _retry?: boolean
  [key: string]: unknown
}

type HttpError<T = ApiErrorResponse> = {
  code?: string
  message?: string
  config?: RequestConfig
  response?: {
    status?: number
    data?: T
  }
}

type HttpInstance = any

type AxiosLike = {
  create: (config: {
    baseURL: string
    withCredentials: boolean
    timeout: number
    headers: Record<string, string>
  }) => HttpInstance
  isAxiosError: (error: unknown) => boolean
}

class ApiClient {
  private readonly axiosLike: AxiosLike
  private readonly instance: HttpInstance
  private isRefreshing = false
  private refreshSubscribers: Array<{
    resolve: () => void
    reject: (error: unknown) => void
  }> = []
  private authFailureHandler?: () => void
  public readonly baseUrl: string

  constructor(axiosLike: AxiosLike, config: ApiClientConfig = {}) {
    this.axiosLike = axiosLike
    this.baseUrl = config.baseUrl || API_BASE_URL

    this.instance = this.axiosLike.create({
      baseURL: this.baseUrl,
      withCredentials: true,
      timeout: 15000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.setupInterceptors()
  }

  private setupInterceptors() {
    this.instance.interceptors.request.use(
      (config: RequestConfig) => {
        if (typeof FormData !== 'undefined' && config.data instanceof FormData && config.headers) {
          delete config.headers['Content-Type']
        }
        return config
      },
      (error: unknown) => Promise.reject(error)
    )

    this.instance.interceptors.response.use(
      (response: unknown) => response,
      async (rawError: unknown) => {
        const error = rawError as HttpError<ApiErrorResponse>
        const originalRequest = (error.config || {}) as RequestConfig & { _retry?: boolean }
        const requestUrl = originalRequest?.url ?? ''
        const isRefreshRequest = requestUrl.includes('/auth/refresh')

        if (error.response?.status === 401 && !originalRequest._retry && !isRefreshRequest) {
          if (this.isRefreshing) {
            return new Promise<void>((resolve, reject) => {
              this.refreshSubscribers.push({
                resolve,
                reject,
              })
            }).then(() => this.instance.request(originalRequest))
          }

          originalRequest._retry = true
          this.isRefreshing = true

          try {
            await this.refreshToken()
            this.onTokenRefreshed()
            return this.instance.request(originalRequest)
          } catch (refreshError) {
            this.onTokenRefreshFailed(refreshError)
            this.authFailureHandler?.()
            return Promise.reject(refreshError)
          } finally {
            this.isRefreshing = false
          }
        }

        return Promise.reject(error)
      }
    )
  }

  private onTokenRefreshed() {
    this.refreshSubscribers.forEach(({ resolve }) => resolve())
    this.refreshSubscribers = []
  }

  private onTokenRefreshFailed(error: unknown) {
    this.refreshSubscribers.forEach(({ reject }) => reject(error))
    this.refreshSubscribers = []
  }

  private async refreshToken() {
    await this.instance.post('/auth/refresh', {})
  }

  setAuthFailureHandler(handler: () => void) {
    this.authFailureHandler = handler
  }

  async get<T>(url: string, config?: unknown): Promise<T> {
    const response = (await this.instance.get(url, config)) as { data: T }
    return response.data
  }

  async post<T>(url: string, data?: unknown, config?: unknown): Promise<T> {
    const response = (await this.instance.post(url, data, config)) as { data: T }
    return response.data
  }

  async patch<T>(url: string, data?: unknown, config?: unknown): Promise<T> {
    const response = (await this.instance.patch(url, data, config)) as { data: T }
    return response.data
  }

  async delete<T>(url: string, config?: unknown): Promise<T> {
    const response = (await this.instance.delete(url, config)) as { data: T }
    return response.data
  }
}

export function createApiClientModule(axiosLike: AxiosLike, config: ApiClientConfig = {}) {
  const apiClient = new ApiClient(axiosLike, config)

  const extractApiErrorMessage = (error: unknown, fallback: string): string => {
    if (axiosLike.isAxiosError(error)) {
      const axiosError = error as HttpError<{ detail?: unknown; message?: unknown }>
      if (axiosError.code === 'ECONNABORTED') {
        return '请求超时，请检查后端服务状态'
      }
      const responseData = axiosError.response?.data
      const detail = responseData?.detail
      if (typeof detail === 'string' && detail.trim()) {
        return detail
      }
      if (detail && typeof detail === 'object') {
        const detailObj = detail as { message?: unknown }
        if (typeof detailObj.message === 'string' && detailObj.message.trim()) {
          return detailObj.message
        }
      }
      if (typeof responseData?.message === 'string' && responseData.message.trim()) {
        return responseData.message
      }
    }
    if (error instanceof Error && error.message.trim()) {
      return error.message
    }
    return fallback
  }

  return {
    apiClient,
    extractApiErrorMessage,
  }
}

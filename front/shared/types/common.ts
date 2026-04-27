export interface PaginationParams {
  skip?: number
  limit?: number
  page?: number
  page_size?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

export interface ErrorResponse {
  detail: {
    error_code: string
    message: string
    details?: Record<string, unknown>
  }
}

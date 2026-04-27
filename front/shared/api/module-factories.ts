export type ApiClientLike = {
  get<T>(url: string, config?: unknown): Promise<T>
  post<T>(url: string, data?: unknown, config?: unknown): Promise<T>
  patch<T>(url: string, data?: unknown, config?: unknown): Promise<T>
  delete<T>(url: string, config?: unknown): Promise<T>
}

export interface KnowledgePointQuery {
  page?: number
  page_size?: number
  q?: string
  include_chunks?: boolean
}

export interface QuestionQuery {
  page?: number
  page_size?: number
  bank_id?: string
  q?: string
  question_type?: string
  is_dirty?: boolean
}

export interface AdminUserQuery {
  page?: number
  page_size?: number
  q?: string
  status?: string
}

export interface AdminKnowledgeGraphOptions<TRequestConfig = unknown> {
  includeOrphanQuestions?: boolean
  forceRefresh?: boolean
  requestConfig?: TRequestConfig
}

export function createAuthApi<
  TUser,
  TRegisterRequest,
  TLoginRequest,
  TLoginResponse,
  TRefreshTokenRequest,
  TRefreshTokenResponse,
>(apiClient: ApiClientLike) {
  return {
    register: (data: TRegisterRequest) => apiClient.post<TLoginResponse>('/auth/register', data),
    login: (data: TLoginRequest) => apiClient.post<TLoginResponse>('/auth/login', data),
    refresh: (data?: TRefreshTokenRequest) => apiClient.post<TRefreshTokenResponse>('/auth/refresh', data),
    getMe: () => apiClient.get<TUser>('/auth/me'),
    logout: (data?: { refresh_token?: string }) => apiClient.post<void>('/auth/logout', data),
  }
}

export function createConversationsApi<
  TConversation,
  TCreateConversationRequest,
  TUpdateConversationRequest,
  TConversationListResponse,
  TMessageListResponse,
>(apiClient: ApiClientLike) {
  return {
    list: (params?: { skip?: number; limit?: number }) =>
      apiClient.get<TConversationListResponse>('/conversations', { params }),
    create: (data: TCreateConversationRequest) => apiClient.post<TConversation>('/conversations', data),
    get: (id: string) => apiClient.get<TConversation>(`/conversations/${id}`),
    update: (id: string, data: TUpdateConversationRequest) =>
      apiClient.patch<TConversation>(`/conversations/${id}`, data),
    delete: (id: string) => apiClient.delete<void>(`/conversations/${id}`),
    listMessages: (id: string, params?: { skip?: number; limit?: number }) =>
      apiClient.get<TMessageListResponse>(`/conversations/${id}/messages`, { params }),
  }
}

export function createChatRunsApi<
  TCreateChatRunRequest,
  TChatRun,
  TChatRunStatus = TChatRun,
  TChatRunMutation = TChatRun,
  TResumeChatRunRequest = unknown,
  TChatRunEvents = unknown,
>(
  apiClient: ApiClientLike
) {
  return {
    create: (conversationId: string, data: TCreateChatRunRequest) =>
      apiClient.post<TChatRun>(`/conversations/${conversationId}/runs`, data),
    get: (conversationId: string, runId: string) =>
      apiClient.get<TChatRunStatus>(`/conversations/${conversationId}/runs/${runId}`),
    listEvents: (conversationId: string, runId: string, params?: { after_event_id?: string }) =>
      apiClient.get<TChatRunEvents>(`/conversations/${conversationId}/runs/${runId}/events`, { params }),
    interrupt: (conversationId: string, runId: string) =>
      apiClient.post<TChatRunMutation>(`/conversations/${conversationId}/runs/${runId}/interrupt`),
    retry: (conversationId: string, runId: string) =>
      apiClient.post<TChatRunMutation>(`/conversations/${conversationId}/runs/${runId}/retry`),
    regenerate: (conversationId: string, runId: string) =>
      apiClient.post<TChatRunMutation>(`/conversations/${conversationId}/runs/${runId}/regenerate`),
    resume: (conversationId: string, runId: string, data: TResumeChatRunRequest) =>
      apiClient.post<TChatRunMutation>(`/conversations/${conversationId}/runs/${runId}/resume`, data),
  }
}

export function createAdminIngestionApi<
  TPresignUploadRequest,
  TPresignUploadResponse,
  TUploadCallbackRequest,
  TUploadCallbackResponse,
  TKnowledgePointCreate,
  TKnowledgePointUpdate,
  TKnowledgePointListResponse,
  TKnowledgePointResponse,
  TKnowledgePointDeleteResponse,
  TKnowledgePointDocumentUrlResponse,
  TIngestionJobResponse,
  TIngestionJobRetryResponse,
>(apiClient: ApiClientLike) {
  return {
    presignUpload: (data: TPresignUploadRequest) =>
      apiClient.post<TPresignUploadResponse>('/admin/uploads/presign', data),
    uploadCallback: (data: TUploadCallbackRequest) =>
      apiClient.post<TUploadCallbackResponse>('/admin/uploads/callback', data),
    getKnowledgePoints: (params?: KnowledgePointQuery) => {
      const queryParams = new URLSearchParams()
      if (params?.page !== undefined) queryParams.append('page', params.page.toString())
      if (params?.page_size !== undefined) queryParams.append('page_size', params.page_size.toString())
      if (params?.q) queryParams.append('q', params.q)
      if (params?.include_chunks !== undefined) queryParams.append('include_chunks', String(params.include_chunks))

      const queryString = queryParams.toString() ? `?${queryParams.toString()}` : ''
      return apiClient.get<TKnowledgePointListResponse>(`/admin/knowledge-points${queryString}`)
    },
    createKnowledgePoint: (data: TKnowledgePointCreate) =>
      apiClient.post<TKnowledgePointResponse>('/admin/knowledge-points', data),
    getKnowledgePoint: (id: string) =>
      apiClient.get<TKnowledgePointResponse>(`/admin/knowledge-points/${id}`),
    deleteKnowledgePoint: (id: string) =>
      apiClient.delete<TKnowledgePointDeleteResponse>(`/admin/knowledge-points/${id}`),
    getKnowledgePointDocumentUrl: (id: string, expiresIn = 3600) =>
      apiClient.get<TKnowledgePointDocumentUrlResponse>(
        `/admin/knowledge-points/${id}/document-url?expires_in=${expiresIn}`
      ),
    updateKnowledgePoint: (id: string, data: TKnowledgePointUpdate) =>
      apiClient.patch<TKnowledgePointResponse>(`/admin/knowledge-points/${id}`, data),
    reindexKnowledgePoint: (id: string) =>
      apiClient.post<TIngestionJobResponse>(`/admin/knowledge-points/${id}/reindex`),
    getIngestionJob: (id: string, signal?: AbortSignal) =>
      apiClient.get<TIngestionJobResponse>(`/admin/ingestion-jobs/${id}`, { signal }),
    retryIngestionJob: (id: string) =>
      apiClient.post<TIngestionJobRetryResponse>(`/admin/ingestion-jobs/${id}/retry`),
  }
}

export function createAdminQuestionsApi<
  TQuestionBankCreate,
  TQuestionBankListResponse,
  TQuestionBankResponse,
  TQuestionBankUpdate,
  TQuestionCreate,
  TQuestionUpdate,
  TQuestionListResponse,
  TQuestionResponse,
  TQuestionImportRequest,
  TQuestionImportResponse,
  TQuestionVectorizeRequest,
  TVectorizationJobResponse,
  TQuestionKnowledgePointLink,
>(apiClient: ApiClientLike) {
  return {
    getQuestionBanks: () => apiClient.get<TQuestionBankListResponse>('/admin/question-banks'),
    createQuestionBank: (data: TQuestionBankCreate) =>
      apiClient.post<TQuestionBankResponse>('/admin/question-banks', data),
    updateQuestionBank: (id: string, data: TQuestionBankUpdate) =>
      apiClient.patch<TQuestionBankResponse>(`/admin/question-banks/${id}`, data),
    deleteQuestionBank: (id: string) => apiClient.delete<void>(`/admin/question-banks/${id}`),
    getQuestions: (params?: QuestionQuery) => {
      const queryParams = new URLSearchParams()
      if (params?.page !== undefined) queryParams.append('page', params.page.toString())
      if (params?.page_size !== undefined) queryParams.append('page_size', params.page_size.toString())
      if (params?.bank_id) queryParams.append('bank_id', params.bank_id)
      if (params?.q) queryParams.append('q', params.q)
      if (params?.question_type) queryParams.append('question_type', params.question_type)
      if (params?.is_dirty !== undefined) queryParams.append('is_dirty', String(params.is_dirty))

      const queryString = queryParams.toString() ? `?${queryParams.toString()}` : ''
      return apiClient.get<TQuestionListResponse>(`/admin/questions${queryString}`)
    },
    createQuestion: (data: TQuestionCreate) => apiClient.post<TQuestionResponse>('/admin/questions', data),
    getQuestion: (id: string) => apiClient.get<TQuestionResponse>(`/admin/questions/${id}`),
    updateQuestion: (id: string, data: TQuestionUpdate) =>
      apiClient.patch<TQuestionResponse>(`/admin/questions/${id}`, data),
    deleteQuestion: (id: string) => apiClient.delete<void>(`/admin/questions/${id}`),
    importQuestions: (data: TQuestionImportRequest | FormData) => {
      if (data instanceof FormData) {
        return apiClient.post<TQuestionImportResponse>('/admin/questions/import', data, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }
      return apiClient.post<TQuestionImportResponse>('/admin/questions/import', data)
    },
    vectorizeQuestions: (data: TQuestionVectorizeRequest) =>
      apiClient.post<TVectorizationJobResponse>('/admin/questions/vectorize', data),
    getVectorizationJob: (id: string) =>
      apiClient.get<TVectorizationJobResponse>(`/admin/questions/vectorize-jobs/${id}`),
    linkKnowledgePoints: (questionId: string, data: TQuestionKnowledgePointLink) =>
      apiClient.post<void>(`/admin/questions/${questionId}/knowledge-points`, data),
    unlinkKnowledgePoint: (questionId: string, knowledgePointId: string) =>
      apiClient.delete<void>(`/admin/questions/${questionId}/knowledge-points/${knowledgePointId}`),
  }
}

export function createAdminUsersApi<
  TAdminUser,
  TAdminUserListResponse,
  TAdminUserStatusUpdateRequest,
  TAdminConversationSummaryListResponse,
  TAdminConversationMessageListResponse,
>(apiClient: ApiClientLike) {
  return {
    getUsers: (params?: AdminUserQuery) => {
      const queryParams = new URLSearchParams()
      if (params?.page !== undefined) queryParams.append('page', params.page.toString())
      if (params?.page_size !== undefined) queryParams.append('page_size', params.page_size.toString())
      if (params?.q) queryParams.append('q', params.q)
      if (params?.status) queryParams.append('status', params.status)

      const queryString = queryParams.toString() ? `?${queryParams.toString()}` : ''
      return apiClient.get<TAdminUserListResponse>(`/admin/users${queryString}`)
    },
    getUser: (id: string) => apiClient.get<TAdminUser>(`/admin/users/${id}`),
    updateUserStatus: (id: string, data: TAdminUserStatusUpdateRequest) =>
      apiClient.patch<TAdminUser>(`/admin/users/${id}/status`, data),
    listUserConversations: (userId: string, params?: { page?: number; page_size?: number }) => {
      const queryParams = new URLSearchParams()
      if (params?.page !== undefined) queryParams.append('page', params.page.toString())
      if (params?.page_size !== undefined) queryParams.append('page_size', params.page_size.toString())

      const queryString = queryParams.toString() ? `?${queryParams.toString()}` : ''
      return apiClient.get<TAdminConversationSummaryListResponse>(`/admin/users/${userId}/conversations${queryString}`)
    },
    listConversationMessages: (
      userId: string,
      conversationId: string,
      params?: { page?: number; page_size?: number }
    ) => {
      const queryParams = new URLSearchParams()
      if (params?.page !== undefined) queryParams.append('page', params.page.toString())
      if (params?.page_size !== undefined) queryParams.append('page_size', params.page_size.toString())

      const queryString = queryParams.toString() ? `?${queryParams.toString()}` : ''
      return apiClient.get<TAdminConversationMessageListResponse>(
        `/admin/users/${userId}/conversations/${conversationId}/messages${queryString}`
      )
    },
  }
}

export function createAdminAnalyticsApi<TAdminDashboardResponse, TAdminRange, TKnowledgeGraphResponse, TRequestConfig>(
  apiClient: ApiClientLike
) {
  return {
    getAdminDashboard: (range: TAdminRange) =>
      apiClient.get<TAdminDashboardResponse>(`/admin/dashboard?range=${String(range)}`),
    getKnowledgeGraph: (
      range: TAdminRange,
      nodeLimit = 200,
      options?: AdminKnowledgeGraphOptions<TRequestConfig>
    ) => {
      const includeOrphanQuestions = options?.includeOrphanQuestions ?? true
      const forceRefresh = options?.forceRefresh ?? false

      return apiClient.get<TKnowledgeGraphResponse>(
        `/admin/knowledge-graph?range=${String(range)}&node_limit=${nodeLimit}&include_orphan_questions=${String(includeOrphanQuestions)}&force_refresh=${String(forceRefresh)}`,
        options?.requestConfig
      )
    },
  }
}

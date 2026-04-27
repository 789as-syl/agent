"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createAuthApi = createAuthApi;
exports.createConversationsApi = createConversationsApi;
exports.createChatRunsApi = createChatRunsApi;
exports.createAdminIngestionApi = createAdminIngestionApi;
exports.createAdminQuestionsApi = createAdminQuestionsApi;
exports.createAdminUsersApi = createAdminUsersApi;
exports.createAdminAnalyticsApi = createAdminAnalyticsApi;
function createAuthApi(apiClient) {
    return {
        register: (data) => apiClient.post('/auth/register', data),
        login: (data) => apiClient.post('/auth/login', data),
        refresh: (data) => apiClient.post('/auth/refresh', data),
        getMe: () => apiClient.get('/auth/me'),
        logout: (data) => apiClient.post('/auth/logout', data),
    };
}
function createConversationsApi(apiClient) {
    return {
        list: (params) => apiClient.get('/conversations', { params }),
        create: (data) => apiClient.post('/conversations', data),
        get: (id) => apiClient.get(`/conversations/${id}`),
        update: (id, data) => apiClient.patch(`/conversations/${id}`, data),
        delete: (id) => apiClient.delete(`/conversations/${id}`),
        listMessages: (id, params) => apiClient.get(`/conversations/${id}/messages`, { params }),
    };
}
function createChatRunsApi(apiClient) {
    return {
        create: (conversationId, data) => apiClient.post(`/conversations/${conversationId}/runs`, data),
        get: (conversationId, runId) => apiClient.get(`/conversations/${conversationId}/runs/${runId}`),
        listEvents: (conversationId, runId, params) => apiClient.get(`/conversations/${conversationId}/runs/${runId}/events`, { params }),
        interrupt: (conversationId, runId) => apiClient.post(`/conversations/${conversationId}/runs/${runId}/interrupt`),
        retry: (conversationId, runId) => apiClient.post(`/conversations/${conversationId}/runs/${runId}/retry`),
        regenerate: (conversationId, runId) => apiClient.post(`/conversations/${conversationId}/runs/${runId}/regenerate`),
        resume: (conversationId, runId, data) => apiClient.post(`/conversations/${conversationId}/runs/${runId}/resume`, data),
    };
}
function createAdminIngestionApi(apiClient) {
    return {
        presignUpload: (data) => apiClient.post('/admin/uploads/presign', data),
        uploadCallback: (data) => apiClient.post('/admin/uploads/callback', data),
        getKnowledgePoints: (params) => {
            const queryParams = new URLSearchParams();
            if (params?.page !== undefined)
                queryParams.append('page', params.page.toString());
            if (params?.page_size !== undefined)
                queryParams.append('page_size', params.page_size.toString());
            if (params?.q)
                queryParams.append('q', params.q);
            if (params?.include_chunks !== undefined)
                queryParams.append('include_chunks', String(params.include_chunks));
            const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
            return apiClient.get(`/admin/knowledge-points${queryString}`);
        },
        createKnowledgePoint: (data) => apiClient.post('/admin/knowledge-points', data),
        getKnowledgePoint: (id) => apiClient.get(`/admin/knowledge-points/${id}`),
        deleteKnowledgePoint: (id) => apiClient.delete(`/admin/knowledge-points/${id}`),
        getKnowledgePointDocumentUrl: (id, expiresIn = 3600) => apiClient.get(`/admin/knowledge-points/${id}/document-url?expires_in=${expiresIn}`),
        updateKnowledgePoint: (id, data) => apiClient.patch(`/admin/knowledge-points/${id}`, data),
        reindexKnowledgePoint: (id) => apiClient.post(`/admin/knowledge-points/${id}/reindex`),
        getIngestionJob: (id, signal) => apiClient.get(`/admin/ingestion-jobs/${id}`, { signal }),
        retryIngestionJob: (id) => apiClient.post(`/admin/ingestion-jobs/${id}/retry`),
    };
}
function createAdminQuestionsApi(apiClient) {
    return {
        getQuestionBanks: () => apiClient.get('/admin/question-banks'),
        createQuestionBank: (data) => apiClient.post('/admin/question-banks', data),
        updateQuestionBank: (id, data) => apiClient.patch(`/admin/question-banks/${id}`, data),
        deleteQuestionBank: (id) => apiClient.delete(`/admin/question-banks/${id}`),
        getQuestions: (params) => {
            const queryParams = new URLSearchParams();
            if (params?.page !== undefined)
                queryParams.append('page', params.page.toString());
            if (params?.page_size !== undefined)
                queryParams.append('page_size', params.page_size.toString());
            if (params?.bank_id)
                queryParams.append('bank_id', params.bank_id);
            if (params?.q)
                queryParams.append('q', params.q);
            if (params?.question_type)
                queryParams.append('question_type', params.question_type);
            if (params?.is_dirty !== undefined)
                queryParams.append('is_dirty', String(params.is_dirty));
            const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
            return apiClient.get(`/admin/questions${queryString}`);
        },
        createQuestion: (data) => apiClient.post('/admin/questions', data),
        getQuestion: (id) => apiClient.get(`/admin/questions/${id}`),
        updateQuestion: (id, data) => apiClient.patch(`/admin/questions/${id}`, data),
        deleteQuestion: (id) => apiClient.delete(`/admin/questions/${id}`),
        importQuestions: (data) => {
            if (data instanceof FormData) {
                return apiClient.post('/admin/questions/import', data, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
            }
            return apiClient.post('/admin/questions/import', data);
        },
        vectorizeQuestions: (data) => apiClient.post('/admin/questions/vectorize', data),
        getVectorizationJob: (id) => apiClient.get(`/admin/questions/vectorize-jobs/${id}`),
        linkKnowledgePoints: (questionId, data) => apiClient.post(`/admin/questions/${questionId}/knowledge-points`, data),
        unlinkKnowledgePoint: (questionId, knowledgePointId) => apiClient.delete(`/admin/questions/${questionId}/knowledge-points/${knowledgePointId}`),
    };
}
function createAdminUsersApi(apiClient) {
    return {
        getUsers: (params) => {
            const queryParams = new URLSearchParams();
            if (params?.page !== undefined)
                queryParams.append('page', params.page.toString());
            if (params?.page_size !== undefined)
                queryParams.append('page_size', params.page_size.toString());
            if (params?.q)
                queryParams.append('q', params.q);
            if (params?.status)
                queryParams.append('status', params.status);
            const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
            return apiClient.get(`/admin/users${queryString}`);
        },
        getUser: (id) => apiClient.get(`/admin/users/${id}`),
        updateUserStatus: (id, data) => apiClient.patch(`/admin/users/${id}/status`, data),
        listUserConversations: (userId, params) => {
            const queryParams = new URLSearchParams();
            if (params?.page !== undefined)
                queryParams.append('page', params.page.toString());
            if (params?.page_size !== undefined)
                queryParams.append('page_size', params.page_size.toString());
            const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
            return apiClient.get(`/admin/users/${userId}/conversations${queryString}`);
        },
        listConversationMessages: (userId, conversationId, params) => {
            const queryParams = new URLSearchParams();
            if (params?.page !== undefined)
                queryParams.append('page', params.page.toString());
            if (params?.page_size !== undefined)
                queryParams.append('page_size', params.page_size.toString());
            const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
            return apiClient.get(`/admin/users/${userId}/conversations/${conversationId}/messages${queryString}`);
        },
    };
}
function createAdminAnalyticsApi(apiClient) {
    return {
        getAdminDashboard: (range) => apiClient.get(`/admin/dashboard?range=${String(range)}`),
        getKnowledgeGraph: (range, nodeLimit = 200, options) => {
            const includeOrphanQuestions = options?.includeOrphanQuestions ?? true;
            const forceRefresh = options?.forceRefresh ?? false;
            return apiClient.get(`/admin/knowledge-graph?range=${String(range)}&node_limit=${nodeLimit}&include_orphan_questions=${String(includeOrphanQuestions)}&force_refresh=${String(forceRefresh)}`, options?.requestConfig);
        },
    };
}

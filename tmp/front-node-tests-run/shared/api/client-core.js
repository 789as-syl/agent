"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createApiClientModule = createApiClientModule;
const API_BASE_URL = '/api/v1';
class ApiClient {
    constructor(axiosLike, config = {}) {
        Object.defineProperty(this, "axiosLike", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "instance", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "token", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "isRefreshing", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: false
        });
        Object.defineProperty(this, "refreshSubscribers", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: []
        });
        Object.defineProperty(this, "authFailureHandler", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "baseUrl", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        this.axiosLike = axiosLike;
        this.baseUrl = config.baseUrl || API_BASE_URL;
        this.token = config.token;
        this.instance = this.axiosLike.create({
            baseURL: this.baseUrl,
            withCredentials: true,
            timeout: 15000,
            headers: {
                'Content-Type': 'application/json',
            },
        });
        this.setupInterceptors();
    }
    setupInterceptors() {
        this.instance.interceptors.request.use((config) => {
            if (typeof FormData !== 'undefined' && config.data instanceof FormData && config.headers) {
                delete config.headers['Content-Type'];
            }
            if (this.token && config.headers) {
                config.headers.Authorization = `Bearer ${this.token}`;
            }
            return config;
        }, (error) => Promise.reject(error));
        this.instance.interceptors.response.use((response) => response, async (rawError) => {
            const error = rawError;
            const originalRequest = (error.config || {});
            const requestUrl = originalRequest?.url ?? '';
            const isRefreshRequest = requestUrl.includes('/auth/refresh');
            if (error.response?.status === 401 && !originalRequest._retry && !isRefreshRequest) {
                if (this.isRefreshing) {
                    return new Promise((resolve, reject) => {
                        this.refreshSubscribers.push({
                            resolve: (token) => {
                                if (originalRequest.headers) {
                                    originalRequest.headers.Authorization = `Bearer ${token}`;
                                }
                                resolve(token);
                            },
                            reject,
                        });
                    }).then(() => this.instance.request(originalRequest));
                }
                originalRequest._retry = true;
                this.isRefreshing = true;
                try {
                    const response = await this.refreshToken();
                    const newToken = response.access_token;
                    this.setToken(newToken);
                    this.onTokenRefreshed(newToken);
                    if (originalRequest.headers) {
                        originalRequest.headers.Authorization = `Bearer ${newToken}`;
                    }
                    return this.instance.request(originalRequest);
                }
                catch (refreshError) {
                    this.clearToken();
                    this.onTokenRefreshFailed(refreshError);
                    this.authFailureHandler?.();
                    return Promise.reject(refreshError);
                }
                finally {
                    this.isRefreshing = false;
                }
            }
            return Promise.reject(error);
        });
    }
    onTokenRefreshed(token) {
        this.refreshSubscribers.forEach(({ resolve }) => resolve(token));
        this.refreshSubscribers = [];
    }
    onTokenRefreshFailed(error) {
        this.refreshSubscribers.forEach(({ reject }) => reject(error));
        this.refreshSubscribers = [];
    }
    async refreshToken() {
        const response = (await this.instance.post('/auth/refresh', {}));
        return response.data;
    }
    setToken(token) {
        this.token = token;
    }
    clearToken() {
        this.token = undefined;
    }
    setAuthFailureHandler(handler) {
        this.authFailureHandler = handler;
    }
    getToken() {
        return this.token;
    }
    async get(url, config) {
        const response = (await this.instance.get(url, config));
        return response.data;
    }
    async post(url, data, config) {
        const response = (await this.instance.post(url, data, config));
        return response.data;
    }
    async patch(url, data, config) {
        const response = (await this.instance.patch(url, data, config));
        return response.data;
    }
    async delete(url, config) {
        const response = (await this.instance.delete(url, config));
        return response.data;
    }
}
function createApiClientModule(axiosLike, config = {}) {
    const apiClient = new ApiClient(axiosLike, config);
    const extractApiErrorMessage = (error, fallback) => {
        if (axiosLike.isAxiosError(error)) {
            const axiosError = error;
            if (axiosError.code === 'ECONNABORTED') {
                return '请求超时，请检查后端服务状态';
            }
            const responseData = axiosError.response?.data;
            const detail = responseData?.detail;
            if (typeof detail === 'string' && detail.trim()) {
                return detail;
            }
            if (detail && typeof detail === 'object') {
                const detailObj = detail;
                if (typeof detailObj.message === 'string' && detailObj.message.trim()) {
                    return detailObj.message;
                }
            }
            if (typeof responseData?.message === 'string' && responseData.message.trim()) {
                return responseData.message;
            }
        }
        if (error instanceof Error && error.message.trim()) {
            return error.message;
        }
        return fallback;
    };
    return {
        apiClient,
        extractApiErrorMessage,
    };
}

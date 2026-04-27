"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sseClient = exports.SSEClient = void 0;
const API_BASE_URL = '/api/v1';
const PRIMARY_EVENT_TYPES = [
    'execution_trace',
    'reasoning_delta',
    'generation_delta',
    'final_answer',
    'hitl_requested',
    'hitl_resolved',
    'done',
    'error',
];
const PLAYBACK_CURSOR_EVENT_TYPES = new Set([
    'execution_trace',
    'reasoning_delta',
    'generation_delta',
    'final_answer',
    'hitl_requested',
    'hitl_resolved',
    'done',
    'error',
]);
const TERMINAL_EVENT_TYPES = new Set([
    'done',
    'error',
    'hitl_requested',
]);
class SSEClient {
    constructor(config = {}) {
        Object.defineProperty(this, "baseUrl", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "maxReconnectAttempts", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "reconnectDelay", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "eventSource", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "reconnectTimer", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        // Last persisted playback event returned by stream/events APIs.
        Object.defineProperty(this, "lastEventId", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "reconnectAttempts", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: 0
        });
        Object.defineProperty(this, "isManualClose", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: false
        });
        Object.defineProperty(this, "terminalEventReceived", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: false
        });
        Object.defineProperty(this, "processedEventIds", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: new Set()
        });
        Object.defineProperty(this, "processedEventQueue", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: []
        });
        Object.defineProperty(this, "maxProcessedEventIds", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: 1000
        });
        Object.defineProperty(this, "currentConversationId", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "currentRunId", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "onEventCallback", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "onErrorCallback", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "onOpenCallback", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        Object.defineProperty(this, "reconnectGuard", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        this.baseUrl = config.baseUrl || API_BASE_URL;
        this.maxReconnectAttempts = config.maxReconnectAttempts || 5;
        this.reconnectDelay = config.reconnectDelay || 1000;
    }
    onEvent(callback) {
        this.onEventCallback = callback;
    }
    onError(callback) {
        this.onErrorCallback = callback;
    }
    onOpen(callback) {
        this.onOpenCallback = callback;
    }
    setToken(token) {
        void token;
    }
    setReconnectGuard(guard) {
        this.reconnectGuard = guard;
    }
    connect(conversationId, runId, lastEventId) {
        this.disconnect();
        this.isManualClose = false;
        this.terminalEventReceived = false;
        this.reconnectAttempts = 0;
        this.currentConversationId = conversationId;
        this.currentRunId = runId;
        this.lastEventId = lastEventId || undefined;
        this.processedEventIds.clear();
        this.processedEventQueue = [];
        this.createEventSource(conversationId, runId);
    }
    createEventSource(conversationId, runId) {
        if (this.eventSource) {
            this.eventSource.close();
        }
        if (this.reconnectTimer) {
            window.clearTimeout(this.reconnectTimer);
            this.reconnectTimer = undefined;
        }
        const url = new URL(`${this.baseUrl}/conversations/${conversationId}/runs/${runId}/stream`, window.location.origin);
        this.eventSource = new EventSource(url.toString(), { withCredentials: true });
        this.eventSource.onopen = () => {
            this.reconnectAttempts = 0;
            if (this.onOpenCallback) {
                this.onOpenCallback();
            }
        };
        const eventTypes = [...PRIMARY_EVENT_TYPES];
        eventTypes.forEach((eventType) => {
            this.eventSource.addEventListener(eventType, (event) => {
                const messageEvent = event;
                try {
                    const normalized = normalizeSSEEvent(JSON.parse(messageEvent.data));
                    if (!normalized) {
                        return;
                    }
                    if (normalized.event_id && PLAYBACK_CURSOR_EVENT_TYPES.has(normalized.event_type)) {
                        this.lastEventId = normalized.event_id;
                    }
                    if (normalized.event_id) {
                        if (this.processedEventIds.has(normalized.event_id)) {
                            return;
                        }
                        this.processedEventIds.add(normalized.event_id);
                        this.processedEventQueue.push(normalized.event_id);
                        if (this.processedEventQueue.length > this.maxProcessedEventIds) {
                            const staleId = this.processedEventQueue.shift();
                            if (staleId) {
                                this.processedEventIds.delete(staleId);
                            }
                        }
                    }
                    if (this.onEventCallback) {
                        this.onEventCallback(normalized);
                    }
                    if (TERMINAL_EVENT_TYPES.has(normalized.event_type)) {
                        this.terminalEventReceived = true;
                        this.closeCurrentStream();
                    }
                }
                catch (error) {
                    console.error(`Failed to parse SSE event [${eventType}]`, error);
                }
            });
        });
        this.eventSource.onerror = (error) => {
            if (this.isManualClose || this.terminalEventReceived) {
                return;
            }
            const readyState = this.eventSource?.readyState;
            if (readyState === EventSource.CONNECTING) {
                return;
            }
            if (readyState === EventSource.CLOSED) {
                void this.handleReconnect(conversationId, runId, error);
                return;
            }
            this.notifyError(error);
        };
    }
    async handleReconnect(conversationId, runId, error) {
        if (this.terminalEventReceived) {
            this.closeCurrentStream();
            return;
        }
        if (this.reconnectGuard) {
            try {
                const shouldReconnect = await this.reconnectGuard(conversationId, runId);
                if (!shouldReconnect) {
                    this.closeCurrentStream();
                    this.notifyError(error);
                    return;
                }
            }
            catch {
                this.closeCurrentStream();
                this.notifyError(error);
                return;
            }
        }
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached');
            this.notifyError(error);
            return;
        }
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        this.reconnectTimer = window.setTimeout(() => {
            if (!this.isManualClose) {
                this.createEventSource(conversationId, runId);
            }
            this.reconnectTimer = undefined;
        }, delay);
    }
    disconnect() {
        this.isManualClose = true;
        this.terminalEventReceived = false;
        this.processedEventIds.clear();
        this.processedEventQueue = [];
        this.currentConversationId = undefined;
        this.currentRunId = undefined;
        this.closeCurrentStream();
    }
    notifyError(error) {
        if (this.onErrorCallback) {
            this.onErrorCallback(error);
        }
    }
    resetLastEventId() {
        this.lastEventId = undefined;
    }
    getLastEventId() {
        return this.lastEventId;
    }
    setLastEventId(eventId) {
        this.lastEventId = eventId;
    }
    closeCurrentStream() {
        if (this.reconnectTimer) {
            window.clearTimeout(this.reconnectTimer);
            this.reconnectTimer = undefined;
        }
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = undefined;
        }
    }
}
exports.SSEClient = SSEClient;
function normalizeSSEEvent(value) {
    if (!isRecord(value))
        return null;
    const normalizedEventType = normalizeEventType(readString(value.event_type));
    if (!normalizedEventType)
        return null;
    const eventId = readString(value.event_id);
    const requestId = readString(value.request_id);
    const conversationId = readString(value.conversation_id);
    const timestamp = readString(value.timestamp);
    const step = typeof value.step === 'number' ? value.step : Number(value.step);
    if (!eventId || !requestId || !conversationId || !timestamp || !Number.isFinite(step)) {
        return null;
    }
    return {
        event_id: eventId,
        request_id: requestId,
        conversation_id: conversationId,
        event_type: normalizedEventType,
        step,
        timestamp,
        is_final: Boolean(value.is_final),
        trace_data: normalizeTraceData(normalizedEventType, value.trace_data),
    };
}
function normalizeEventType(eventType) {
    if (!eventType)
        return null;
    if (PRIMARY_EVENT_TYPES.includes(eventType)) {
        return eventType;
    }
    return null;
}
function normalizeTraceData(eventType, rawTraceData) {
    const trace = isRecord(rawTraceData) ? rawTraceData : {};
    switch (eventType) {
        case 'hitl_requested':
            return {
                kind: readString(trace.kind) || 'clarification',
                prompt: readString(trace.prompt) || readString(trace.question) || '请补充必要信息',
                allowed_actions: normalizeAllowedActions(trace.allowed_actions),
            };
        case 'hitl_resolved':
            return {
                kind: readString(trace.kind) || 'clarification',
            };
        case 'execution_trace':
            return {
                kind: readString(trace.kind) || 'execution',
                title: readString(trace.title) || readString(trace.tool_name) || '执行轨迹',
                detail: readString(trace.detail) || readString(trace.result_summary),
                status: readString(trace.status) || 'completed',
                tool_name: readString(trace.tool_name),
                tool_input: isRecord(trace.tool_input) ? trace.tool_input : undefined,
                result_summary: readString(trace.result_summary),
                result_count: typeof trace.result_count === 'number' ? trace.result_count : undefined,
                retrieval_failed: typeof trace.retrieval_failed === 'boolean' ? trace.retrieval_failed : undefined,
                metadata: isRecord(trace.metadata) ? trace.metadata : undefined,
            };
        case 'reasoning_delta':
            return {
                delta: readString(trace.delta) || '',
                accumulated: readString(trace.accumulated) || undefined,
                source: readString(trace.source) || undefined,
                truncated: typeof trace.truncated === 'boolean' ? trace.truncated : false,
            };
        default:
            return trace;
    }
}
function normalizeAllowedActions(value) {
    if (!Array.isArray(value)) {
        return ['respond'];
    }
    const actions = value
        .map((item) => (typeof item === 'string' ? item : null))
        .filter((item) => (item === 'respond' || item === 'approve' || item === 'edit' || item === 'reject'));
    return actions.length > 0 ? actions : ['respond'];
}
function isRecord(value) {
    return typeof value === 'object' && value !== null;
}
function readString(value) {
    return typeof value === 'string' && value.trim() ? value : null;
}
exports.sseClient = new SSEClient();

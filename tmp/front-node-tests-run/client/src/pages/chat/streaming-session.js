"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createStreamingSessionState = createStreamingSessionState;
exports.restoreStreamingSessionFromRun = restoreStreamingSessionFromRun;
exports.playbackStreamingEvents = playbackStreamingEvents;
exports.applyStreamingEvent = applyStreamingEvent;
exports.sortPlaybackEvents = sortPlaybackEvents;
function createStreamingSessionState(pendingUserMessage = null) {
    return {
        executionTrace: [],
        contentBlocks: null,
        rawReasoning: '',
        reasoningTruncated: false,
        assistantContent: '',
        finalAnswer: '',
        pendingUserMessage,
        hitl: null,
    };
}
function restoreStreamingSessionFromRun(fallbackUserMessage, runtimeState, existingState, playbackEvents) {
    const baseState = existingState ?? createStreamingSessionState(fallbackUserMessage);
    const nextPendingUserMessage = baseState.pendingUserMessage ?? fallbackUserMessage;
    const playback = resolvePlaybackEvents(playbackEvents);
    const playbackState = playback.length > 0
        ? playbackStreamingEvents({
            ...baseState,
            pendingUserMessage: nextPendingUserMessage,
        }, playback)
        : {
            ...baseState,
            pendingUserMessage: nextPendingUserMessage,
        };
    return {
        ...playbackState,
        pendingUserMessage: nextPendingUserMessage,
        hitl: resolveRuntimeHitl(runtimeState, playbackState.hitl),
    };
}
function playbackStreamingEvents(state, events) {
    return sortPlaybackEvents(events).reduce((current, event) => applyStreamingEvent(current, event), state);
}
function applyStreamingEvent(state, event) {
    switch (event.event_type) {
        case 'execution_trace':
            return upsertTraceEntry(state, buildExecutionTraceEntry(event));
        case 'generation_delta':
            return {
                ...state,
                assistantContent: appendIncrementalText(state.assistantContent, event.trace_data?.delta, event.trace_data?.accumulated),
            };
        case 'reasoning_delta':
            return {
                ...state,
                rawReasoning: appendIncrementalText(state.rawReasoning, event.trace_data?.delta, event.trace_data?.accumulated),
                reasoningTruncated: Boolean(event.trace_data?.truncated),
            };
        case 'final_answer': {
            const answer = event.trace_data?.answer || '';
            return {
                ...state,
                assistantContent: answer,
                finalAnswer: answer,
                contentBlocks: normalizeContentBlocks(event.trace_data?.content_blocks),
                hitl: state.hitl ? { ...state.hitl, pending: false } : null,
            };
        }
        case 'hitl_requested': {
            const allowedActions = normalizeAllowedActions(event.trace_data?.allowed_actions);
            return {
                ...state,
                hitl: {
                    pending: true,
                    kind: event.trace_data?.kind || 'clarification',
                    prompt: event.trace_data?.prompt || '请补充必要信息',
                    allowed_actions: allowedActions,
                },
            };
        }
        case 'hitl_resolved':
            return {
                ...state,
                hitl: state.hitl
                    ? {
                        ...state.hitl,
                        pending: false,
                    }
                    : null,
            };
        case 'error':
            return upsertTraceEntry(state, {
                id: event.event_id,
                kind: 'error',
                title: event.trace_data?.error_code || '运行错误',
                detail: event.trace_data?.error_message || '处理请求时发生错误',
                status: 'error',
                timestamp: Date.parse(event.timestamp) || Date.now(),
            });
        default:
            return state;
    }
}
function resolvePlaybackEvents(explicitPlaybackEvents) {
    if (Array.isArray(explicitPlaybackEvents) && explicitPlaybackEvents.length > 0) {
        return sortPlaybackEvents(explicitPlaybackEvents.filter(isSSEEvent));
    }
    return [];
}
function sortPlaybackEvents(events) {
    return [...events]
        .map((event, index) => ({ event, index }))
        .sort((left, right) => {
        if (left.event.step !== right.event.step) {
            return left.event.step - right.event.step;
        }
        return left.index - right.index;
    })
        .map(({ event }) => event);
}
function resolveRuntimeHitl(runtimeState, fallbackHitl) {
    if (!runtimeState) {
        return fallbackHitl;
    }
    const runtimeHitl = runtimeState.hitl;
    const waitingForHitl = Boolean(runtimeHitl?.pending);
    if (!waitingForHitl) {
        return fallbackHitl;
    }
    const allowedActions = normalizeAllowedActions(runtimeHitl?.allowed_actions);
    return {
        pending: waitingForHitl,
        kind: runtimeHitl?.kind || 'clarification',
        prompt: runtimeHitl?.prompt || fallbackHitl?.prompt || null,
        allowed_actions: allowedActions,
    };
}
function isSSEEvent(value) {
    if (!value || typeof value !== 'object')
        return false;
    const candidate = value;
    return (typeof candidate.event_id === 'string' &&
        typeof candidate.event_type === 'string' &&
        typeof candidate.step === 'number' &&
        typeof candidate.timestamp === 'string');
}
function upsertTraceEntry(state, payload) {
    const existingIndex = state.executionTrace.findIndex((step) => step.id === payload.id);
    if (existingIndex === -1) {
        return {
            ...state,
            executionTrace: [...state.executionTrace, payload],
        };
    }
    const executionTrace = [...state.executionTrace];
    executionTrace[existingIndex] = payload;
    return {
        ...state,
        executionTrace,
    };
}
function buildExecutionTraceEntry(event) {
    const traceData = event.trace_data || {};
    return {
        id: event.event_id,
        kind: traceData.kind || 'execution',
        title: traceData.title || traceData.tool_name || '执行轨迹',
        detail: traceData.detail || traceData.result_summary || normalizeToolInput(traceData.tool_input),
        status: traceData.status || inferExecutionStatus(traceData.kind),
        timestamp: Date.parse(event.timestamp) || Date.now(),
        metadata: traceData.metadata,
    };
}
function normalizeAllowedActions(value) {
    if (!Array.isArray(value)) {
        return ['respond'];
    }
    const actions = value
        .filter((item) => (item === 'respond' || item === 'approve' || item === 'edit' || item === 'reject'));
    return actions.length > 0 ? actions : ['respond'];
}
function normalizeToolInput(value) {
    if (!value || typeof value !== 'object') {
        return undefined;
    }
    try {
        return JSON.stringify(value, null, 2);
    }
    catch {
        return undefined;
    }
}
function normalizeContentBlocks(value) {
    if (!Array.isArray(value)) {
        return null;
    }
    const blocks = value.filter((item) => {
        if (!item || typeof item !== 'object')
            return false;
        const candidate = item;
        return typeof candidate.type === 'string';
    });
    return blocks.length > 0 ? blocks : null;
}
function inferExecutionStatus(kind) {
    if (kind === 'tool_start' || kind === 'tool_progress') {
        return 'running';
    }
    return 'completed';
}
function appendIncrementalText(current, delta, accumulated) {
    if (typeof delta === 'string' && delta.length > 0) {
        return current + delta;
    }
    if (!current && typeof accumulated === 'string' && accumulated.length > 0) {
        return accumulated;
    }
    return current;
}

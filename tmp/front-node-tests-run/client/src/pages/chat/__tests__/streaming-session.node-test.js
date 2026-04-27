"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const streaming_session_1 = require("../streaming-session");
function buildEvent(event) {
    return {
        event_id: event.event_id ?? `event-${event.step}`,
        request_id: event.request_id ?? 'req-1',
        conversation_id: event.conversation_id ?? 'conv-1',
        event_type: event.event_type,
        step: event.step,
        timestamp: event.timestamp ?? new Date(0).toISOString(),
        is_final: event.is_final ?? false,
        trace_data: event.trace_data ?? {},
    };
}
(0, node_test_1.default)('applyStreamingEvent treats delta as source of truth over stale accumulated payloads', () => {
    const state = {
        ...(0, streaming_session_1.createStreamingSessionState)(),
        assistantContent: 'hel',
        rawReasoning: 'thin',
    };
    const nextAnswerState = (0, streaming_session_1.applyStreamingEvent)(state, buildEvent({
        event_type: 'generation_delta',
        step: 2,
        trace_data: {
            delta: 'lo',
            accumulated: 'stale-answer',
        },
    }));
    const nextReasoningState = (0, streaming_session_1.applyStreamingEvent)(nextAnswerState, buildEvent({
        event_type: 'reasoning_delta',
        step: 3,
        trace_data: {
            delta: 'king',
            accumulated: 'stale-reasoning',
            truncated: false,
        },
    }));
    strict_1.default.equal(nextAnswerState.assistantContent, 'hello');
    strict_1.default.equal(nextReasoningState.rawReasoning, 'thinking');
});
(0, node_test_1.default)('playbackStreamingEvents replays ordered batches incrementally', () => {
    const events = (0, streaming_session_1.sortPlaybackEvents)([
        buildEvent({
            event_type: 'final_answer',
            step: 4,
            trace_data: {
                answer: 'Hello world',
                content_blocks: [{ type: 'text', text: 'Hello world' }],
            },
        }),
        buildEvent({
            event_type: 'execution_trace',
            step: 3,
            trace_data: {
                kind: 'reasoning',
                title: '开始直接回答',
                detail: 'streaming',
                status: 'completed',
            },
        }),
        buildEvent({
            event_type: 'generation_delta',
            step: 1,
            trace_data: {
                delta: 'Hello',
            },
        }),
        buildEvent({
            event_type: 'reasoning_delta',
            step: 2,
            trace_data: {
                delta: 'thinking',
                truncated: false,
            },
        }),
    ]);
    const baseState = (0, streaming_session_1.createStreamingSessionState)();
    const firstBatch = (0, streaming_session_1.playbackStreamingEvents)(baseState, events.slice(0, 1));
    const secondBatch = (0, streaming_session_1.playbackStreamingEvents)(firstBatch, events.slice(1, 3));
    const finalBatch = (0, streaming_session_1.playbackStreamingEvents)(secondBatch, events.slice(3));
    strict_1.default.equal(firstBatch.assistantContent, 'Hello');
    strict_1.default.equal(firstBatch.rawReasoning, '');
    strict_1.default.equal(secondBatch.rawReasoning, 'thinking');
    strict_1.default.equal(secondBatch.executionTrace.length, 1);
    strict_1.default.equal(finalBatch.finalAnswer, 'Hello world');
    strict_1.default.equal(finalBatch.assistantContent, 'Hello world');
});

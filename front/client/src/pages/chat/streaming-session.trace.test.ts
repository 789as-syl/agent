import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import type { ExecutionTraceEvent } from '../../types'
import type { Message } from '../../types'
import {
  applyStreamingEvent,
  buildExecutionTraceEntry,
  createStreamingSessionState,
  restoreStreamingSessionFromRun,
  resolveExecutionTraceDetail,
} from './streaming-session'
import { buildDisplayMessages, resolveRenderableContent, sanitizeVisibleText } from './message-utils'

function executionTraceEvent(
  traceData: ExecutionTraceEvent['trace_data'] & { semantic_key?: string },
  overrides: Partial<Pick<ExecutionTraceEvent, 'event_id' | 'step' | 'timestamp'>> = {},
): ExecutionTraceEvent {
  return {
    event_id: overrides.event_id ?? 'evt-1',
    request_id: 'req-1',
    conversation_id: 'conv-1',
    event_type: 'execution_trace',
    step: overrides.step ?? 1,
    timestamp: overrides.timestamp ?? '2026-04-22T00:00:00Z',
    is_final: false,
    trace_data: traceData,
  }
}

test('buildExecutionTraceEntry preserves canonical detail, evidence, and reasoning anchor', () => {
  const event = executionTraceEvent({
    kind: 'decision',
    title: '直接回答：本轮未触发工具或澄清',
    detail: '命中信号：商业模式',
    decision_code: 'direct_answer',
    status: 'completed',
    evidence: [{ source: 'classifier', label: '命中问题信号', detail: '商业模式' }],
    reasoning_anchor: { start: 3, end: 8 },
  })

  const entry = buildExecutionTraceEntry(event)

  assert.equal(entry.detail, '命中信号：商业模式')
  assert.equal(entry.decision_code, 'direct_answer')
  assert.equal(entry.evidence?.[0]?.label, '命中问题信号')
  assert.deepEqual(entry.reasoning_anchor, { start: 3, end: 8 })
})

test('buildExecutionTraceEntry reads semantic_key from trace_data', () => {
  const event = executionTraceEvent({
    kind: 'decision',
    title: '语义去重',
    semantic_key: 'trace:decision:direct_answer',
  })

  const entry = buildExecutionTraceEntry(event)

  assert.equal(entry.semantic_key, 'trace:decision:direct_answer')
})

test('applyStreamingEvent upserts by semantic_key even when event_id changes', () => {
  const first = executionTraceEvent(
    {
      kind: 'tool_start',
      title: '检索开始',
      semantic_key: 'trace:tool:retrieve',
      detail: 'round 1',
    },
    { event_id: 'evt-1', step: 1 },
  )
  const second = executionTraceEvent(
    {
      kind: 'tool_finish',
      title: '检索完成',
      semantic_key: 'trace:tool:retrieve',
      detail: 'round 2',
      status: 'completed',
    },
    { event_id: 'evt-2', step: 2 },
  )

  const afterFirst = applyStreamingEvent(createStreamingSessionState(), first)
  const afterSecond = applyStreamingEvent(afterFirst, second)

  assert.equal(afterSecond.executionTrace.length, 1)
  assert.equal(afterSecond.executionTrace[0]?.id, 'evt-2')
  assert.equal(afterSecond.executionTrace[0]?.semantic_key, 'trace:tool:retrieve')
  assert.equal(afterSecond.executionTrace[0]?.detail, 'round 2')
})

test('applyStreamingEvent keeps entries with different semantic_key', () => {
  const first = executionTraceEvent(
    {
      kind: 'tool_start',
      title: '检索开始',
      semantic_key: 'trace:tool:retrieve:a',
    },
    { event_id: 'evt-a', step: 1 },
  )
  const second = executionTraceEvent(
    {
      kind: 'tool_start',
      title: '检索开始2',
      semantic_key: 'trace:tool:retrieve:b',
    },
    { event_id: 'evt-b', step: 2 },
  )

  const afterFirst = applyStreamingEvent(createStreamingSessionState(), first)
  const afterSecond = applyStreamingEvent(afterFirst, second)

  assert.equal(afterSecond.executionTrace.length, 2)
  assert.equal(afterSecond.executionTrace[0]?.id, 'evt-a')
  assert.equal(afterSecond.executionTrace[1]?.id, 'evt-b')
})

test('applyStreamingEvent falls back to id upsert when semantic_key is missing', () => {
  const first = executionTraceEvent(
    {
      kind: 'tool_start',
      title: '无语义键-开始',
      detail: 'first',
    },
    { event_id: 'evt-fallback', step: 1 },
  )
  const second = executionTraceEvent(
    {
      kind: 'tool_finish',
      title: '无语义键-完成',
      detail: 'second',
      status: 'completed',
    },
    { event_id: 'evt-fallback', step: 2 },
  )

  const afterFirst = applyStreamingEvent(createStreamingSessionState(), first)
  const afterSecond = applyStreamingEvent(afterFirst, second)

  assert.equal(afterSecond.executionTrace.length, 1)
  assert.equal(afterSecond.executionTrace[0]?.id, 'evt-fallback')
  assert.equal(afterSecond.executionTrace[0]?.detail, 'second')
})

test('resolveExecutionTraceDetail falls back to legacy result_summary', () => {
  const detail = resolveExecutionTraceDetail({
    result_summary: 'legacy summary only',
  })

  assert.equal(detail, 'legacy summary only')
})

test('resolveExecutionTraceDetail falls back to metadata tool_input when detail is absent', () => {
  const detail = resolveExecutionTraceDetail({
    metadata: {
      tool_input: {
        query: '融资风险',
      },
    },
  })

  assert.equal(detail, '融资风险')
})

test('resolveRenderableContent skips tool protocol blocks instead of rendering raw JSON', () => {
  const message: Message = {
    id: 'assistant-1',
    conversation_id: 'conv-1',
    role: 'assistant',
    content: '',
    created_at: '2026-04-22T00:00:00Z',
    content_blocks: [
      {
        type: 'tool_result',
        tool: 'knowledge_retrieval',
        protocol_version: 'native-v1',
        retrieval_failed: true,
        payload: {
          error: 'DashScope embedding request failed: ConnectionResetError(10054)',
        },
      },
      { type: 'text', text: '安全回答正文' },
    ],
  }

  const content = resolveRenderableContent(message, false)

  assert.equal(content, '安全回答正文')
  assert.equal(content.includes('DashScope embedding request failed'), false)
  assert.equal(content.includes('knowledge_retrieval'), false)
})

test('resolveRenderableContent does not stringify unknown object blocks', () => {
  const message: Message = {
    id: 'assistant-2',
    conversation_id: 'conv-1',
    role: 'assistant',
    content: '',
    created_at: '2026-04-22T00:00:00Z',
    content_blocks: [{ type: 'unknown', value: { nested: true } }],
  }

  assert.equal(resolveRenderableContent(message, false), '')
  assert.equal(resolveRenderableContent(message, true), '正在生成回答...')
})


test('buildDisplayMessages keeps temporary assistant visible after done when only assistantContent is available', () => {
  const state = createStreamingSessionState()
  const displayMessages = buildDisplayMessages(
    [
      {
        id: 'user-1',
        conversation_id: 'conv-1',
        role: 'user',
        content: '问题',
        created_at: '2026-04-22T00:00:00Z',
      },
    ],
    {
      isRunning: false,
      streamingContent: '',
      executionTrace: [],
      conversationId: 'conv-1',
      session: {
        ...state,
        assistantContent: '仅有流式聚合答案',
        finalAnswer: '',
      },
    },
  )

  const streamingAssistant = displayMessages.find((message) => message.id === 'streaming-assistant')
  assert.equal(streamingAssistant?.role, 'assistant')
  assert.equal(streamingAssistant?.content, '仅有流式聚合答案')
})

test('buildDisplayMessages filters stale messages from another conversation after route switch', () => {
  const messages: Message[] = [
    {
      id: 'old-user',
      conversation_id: 'conv-old',
      role: 'user',
      content: '旧会话问题',
      created_at: '2026-04-22T00:00:00Z',
    },
    {
      id: 'new-user',
      conversation_id: 'conv-new',
      role: 'user',
      content: '新会话问题',
      created_at: '2026-04-22T00:00:00Z',
    },
  ]

  const display = buildDisplayMessages(messages, {
    isRunning: false,
    streamingContent: '',
    executionTrace: [],
    conversationId: 'conv-new',
  })

  assert.equal(display.length, 1)
  assert.equal(display[0]?.id, 'new-user')
})


test('buildDisplayMessages does not duplicate temporary assistant after persisted assistant arrives', () => {
  const messages: Message[] = [
    {
      id: 'pending-user',
      conversation_id: 'conv-1',
      role: 'user',
      content: '问题',
      created_at: '2026-04-22T00:00:00Z',
    },
    {
      id: 'assistant-1',
      conversation_id: 'conv-1',
      role: 'assistant',
      content: '持久化答案',
      reply_to_message_id: 'pending-user',
      created_at: '2026-04-22T00:00:01Z',
    },
  ]
  const state = createStreamingSessionState({
    id: 'pending-user',
    content: '问题',
    created_at: '2026-04-22T00:00:00Z',
  })

  const display = buildDisplayMessages(messages, {
    isRunning: false,
    streamingContent: '',
    executionTrace: [],
    conversationId: 'conv-1',
    pendingUserMessage: state.pendingUserMessage,
    session: {
      ...state,
      finalAnswer: '临时答案',
    },
  })

  assert.equal(display.length, 2)
  assert.equal(display.some((message) => message.id === 'streaming-assistant'), false)
  assert.equal(display[1]?.content, '持久化答案')
})


test('sanitizeVisibleText suppresses partial and complete tool protocol JSON', () => {
  assert.equal(
    sanitizeVisibleText('{"success": false, "tool": "knowledge_retrieval", "payload": {'),
    '',
  )
  assert.equal(
    sanitizeVisibleText(
      '{"success": false, "tool": "knowledge_retrieval", "payload": {"error_code": "RETRIEVAL_PROVIDER_UNAVAILABLE"}}商业模式画布是一个分析工具。',
    ),
    '商业模式画布是一个分析工具。',
  )
})

test('applyStreamingEvent keeps direct-answer trace visible and sanitizes JSON deltas', () => {
  const state = createStreamingSessionState()
  const withTrace = applyStreamingEvent(state, executionTraceEvent({
    kind: 'decision',
    title: '直接回答',
    detail: '本轮未调用外部工具，基于模型已有上下文生成回答。',
    decision_code: 'direct_answer',
    status: 'completed',
    semantic_key: 'decision:direct_answer',
  }))
  const withJsonPrefix = applyStreamingEvent(withTrace, {
    event_id: 'evt-json',
    request_id: 'req-1',
    conversation_id: 'conv-1',
    event_type: 'generation_delta',
    step: 2,
    timestamp: '2026-04-22T00:00:01Z',
    is_final: false,
    trace_data: {
      delta: '{"success": false, "tool": "knowledge_retrieval", "payload": {',
    },
  })

  assert.equal(withJsonPrefix.executionTrace.length, 1)
  assert.equal(withJsonPrefix.executionTrace[0]?.decision_code, 'direct_answer')
  assert.equal(withJsonPrefix.assistantContent, '')
})


test('buildDisplayMessages hides pending user after persisted same-content user arrives', () => {
  const state = createStreamingSessionState({
    id: 'pending-user-1',
    content: '同一个问题',
    created_at: '2026-04-22T00:00:00Z',
  })
  const messages: Message[] = [
    {
      id: 'persisted-user-1',
      conversation_id: 'conv-1',
      role: 'user',
      content: '同一个问题',
      created_at: '2026-04-22T00:00:01Z',
    },
    {
      id: 'assistant-1',
      conversation_id: 'conv-1',
      role: 'assistant',
      content: '回答',
      reply_to_message_id: 'persisted-user-1',
      created_at: '2026-04-22T00:00:02Z',
    },
  ]

  const display = buildDisplayMessages(messages, {
    isRunning: false,
    streamingContent: '',
    executionTrace: [],
    conversationId: 'conv-1',
    pendingUserMessage: state.pendingUserMessage,
    session: {
      ...state,
      finalAnswer: '回答',
    },
  })

  assert.equal(display.filter((message) => message.role === 'user').length, 1)
  assert.equal(display.some((message) => message.id === 'pending-user-1'), false)
})

test('buildDisplayMessages hides pending user by stable client_message_id without content matching', () => {
  const state = createStreamingSessionState({
    id: 'pending-user:client-msg-1',
    client_message_id: 'client-msg-1',
    content: '新的问题内容',
    created_at: '2026-04-22T00:00:00Z',
  })
  const messages: Message[] = [
    {
      id: 'persisted-user-1',
      conversation_id: 'conv-1',
      client_message_id: 'client-msg-1',
      role: 'user',
      content: '服务端规范化后的问题内容',
      created_at: '2026-04-22T00:00:01Z',
    },
  ]

  const display = buildDisplayMessages(messages, {
    isRunning: false,
    streamingContent: '',
    executionTrace: [],
    conversationId: 'conv-1',
    activeClientMessageId: 'client-msg-1',
    pendingUserMessage: state.pendingUserMessage,
    session: state,
  })

  assert.equal(display.filter((message) => message.role === 'user').length, 1)
  assert.equal(display[0]?.id, 'persisted-user-1')
  assert.equal(display.some((message) => message.id === 'pending-user:client-msg-1'), false)
})

test('buildDisplayMessages hides streaming assistant by stable association and active run handoff', () => {
  const state = createStreamingSessionState({
    id: 'pending-user:client-msg-2',
    client_message_id: 'client-msg-2',
    content: '原始问题',
    created_at: '2026-04-22T00:00:00Z',
  })
  const messages: Message[] = [
    {
      id: 'persisted-user-2',
      conversation_id: 'conv-1',
      client_message_id: 'client-msg-2',
      role: 'user',
      content: '原始问题',
      created_at: '2026-04-22T00:00:01Z',
    },
    {
      id: 'assistant-2',
      conversation_id: 'conv-1',
      run_id: 'run-2',
      client_message_id: 'client-msg-2',
      role: 'assistant',
      content: '最终持久化回答',
      created_at: '2026-04-22T00:00:02Z',
    },
  ]

  const display = buildDisplayMessages(messages, {
    isRunning: false,
    streamingContent: '',
    executionTrace: [],
    conversationId: 'conv-1',
    activeRunId: 'run-2',
    activeClientMessageId: 'client-msg-2',
    pendingUserMessage: state.pendingUserMessage,
    session: {
      ...state,
      assistantContent: '临时流式回答',
      finalAnswer: '临时流式回答',
    },
  })

  assert.equal(display.some((message) => message.id === 'streaming-assistant'), false)
  assert.equal(display[1]?.id, 'assistant-2')
})


test('buildExecutionTraceEntry preserves answer_basis and structured evidence fields', () => {
  const event = executionTraceEvent({
    kind: 'tool_result',
    title: '知识库命中 1 个证据块',
    detail: '命中证据：商业模式画布',
    decision_code: 'retrieval_hit',
    status: 'completed',
    answer_basis: 'knowledge_backed',
    evidence: [
      {
        source: 'knowledge_retrieval',
        label: '商业模式画布',
        title: '商业模式画布',
        snippet: '用于描述价值主张、客户细分和收入来源的结构化工具。',
        source_type: 'courseware',
        locator: 'page 12',
        evidence_type: 'retrieved_chunk',
      },
    ],
  })

  const entry = buildExecutionTraceEntry(event)

  assert.equal(entry.answer_basis, 'knowledge_backed')
  assert.equal(entry.evidence?.[0]?.title, '商业模式画布')
  assert.equal(entry.evidence?.[0]?.snippet, '用于描述价值主张、客户细分和收入来源的结构化工具。')
  assert.equal(entry.evidence?.[0]?.source_type, 'courseware')
  assert.equal(entry.evidence?.[0]?.locator, 'page 12')
  assert.equal(entry.evidence?.[0]?.evidence_type, 'retrieved_chunk')
})

test('applyStreamingEvent exposes canonical answer_basis instead of raw retrieval failure label', () => {
  const state = applyStreamingEvent(createStreamingSessionState(), executionTraceEvent({
    kind: 'tool_result',
    title: '知识库检索失败',
    detail: '知识库检索暂不可用，已切换为直接回答',
    decision_code: 'retrieval_failed',
    status: 'completed',
    answer_basis: 'retrieval_unavailable',
    retrieval_failed: true,
  }))

  const entry = state.executionTrace[0]
  assert.equal(entry?.answer_basis, 'retrieval_unavailable')
  assert.equal(entry?.decision_code, 'retrieval_failed')
  assert.equal(entry ? 'retrieval_failed' in entry : false, false)
})

test('restoreStreamingSessionFromRun replays answer_basis and evidence the same as live SSE', () => {
  const event = executionTraceEvent({
    kind: 'tool_result',
    title: '知识库命中 1 个证据块',
    decision_code: 'retrieval_hit',
    status: 'completed',
    answer_basis: 'knowledge_backed',
    semantic_key: 'trace:knowledge-backed',
    evidence: [
      {
        source: 'knowledge_retrieval',
        label: '商业模式画布',
        title: '商业模式画布',
        snippet: '紧凑证据摘要',
        source_type: 'courseware',
        locator: 'page 12',
        evidence_type: 'retrieved_chunk',
      },
    ],
  })

  const live = applyStreamingEvent(createStreamingSessionState(), event)
  const hydrated = restoreStreamingSessionFromRun(null, undefined, createStreamingSessionState(), [event])

  assert.deepEqual(hydrated.executionTrace, live.executionTrace)
})

test('legacy direct answer trace falls back to direct answer_basis for protocol compatibility', () => {
  const entry = buildExecutionTraceEntry(executionTraceEvent({
    kind: 'decision',
    title: '直接回答',
    decision_code: 'direct_answer',
    status: 'completed',
  }))

  assert.equal(entry.answer_basis, 'direct')
})

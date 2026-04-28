import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import type { ChatRunStatusResponse, Message, SSEEvent } from '../../types'
import {
  buildPendingUserMessage,
  createChatRunControllerState,
  findHydratedAssistantMessage,
  reduceChatRunControllerState,
  resolveControllerPhaseFromRunStatus,
  type ChatRunControllerState,
} from './chat-run-machine'

function doneEvent(): SSEEvent {
  return {
    event_id: 'evt-done',
    request_id: 'req-1',
    conversation_id: 'conv-1',
    event_type: 'done',
    step: 3,
    timestamp: '2026-04-27T00:00:03Z',
    is_final: true,
    trace_data: {
      total_steps: 3,
      duration_ms: 100,
      success: true,
    },
  }
}

function createStreamingState(): ChatRunControllerState {
  const prepared = reduceChatRunControllerState(createChatRunControllerState('conv-1'), {
    type: 'prepare_send',
    conversationId: 'conv-1',
    clientMessageId: 'client-msg-1',
    pendingUserMessage: buildPendingUserMessage('测试问题', 'client-msg-1'),
  })

  return reduceChatRunControllerState(prepared, {
    type: 'start_streaming',
    conversationId: 'conv-1',
    runId: 'run-1',
    clientMessageId: 'client-msg-1',
    session: prepared.session,
  })
}

test('done event transitions controller to finalizing instead of completed', () => {
  const afterDone = reduceChatRunControllerState(createStreamingState(), {
    type: 'apply_event',
    event: doneEvent(),
  })

  assert.equal(afterDone.phase, 'finalizing')
  assert.equal(afterDone.sseConnectionState, 'closed')
  assert.equal(afterDone.runId, 'run-1')
  assert.equal(afterDone.clientMessageId, 'client-msg-1')
})

test('findHydratedAssistantMessage requires assistant role, matching run_id, and matching client_message_id', () => {
  const messages: Message[] = [
    {
      id: 'user-1',
      conversation_id: 'conv-1',
      run_id: 'run-1',
      client_message_id: 'client-msg-1',
      role: 'user',
      content: '问题',
      created_at: '2026-04-27T00:00:00Z',
    },
    {
      id: 'assistant-wrong-run',
      conversation_id: 'conv-1',
      run_id: 'run-2',
      client_message_id: 'client-msg-1',
      role: 'assistant',
      content: '错误 run',
      created_at: '2026-04-27T00:00:01Z',
    },
    {
      id: 'assistant-wrong-client',
      conversation_id: 'conv-1',
      run_id: 'run-1',
      client_message_id: 'client-msg-2',
      role: 'assistant',
      content: '错误 client',
      created_at: '2026-04-27T00:00:02Z',
    },
    {
      id: 'assistant-match',
      conversation_id: 'conv-1',
      run_id: 'run-1',
      client_message_id: 'client-msg-1',
      role: 'assistant',
      content: '正确命中',
      created_at: '2026-04-27T00:00:03Z',
    },
  ]

  const matched = findHydratedAssistantMessage(messages, {
    conversationId: 'conv-1',
    runId: 'run-1',
    clientMessageId: 'client-msg-1',
  })

  assert.equal(matched?.id, 'assistant-match')
})

test('findHydratedAssistantMessage stays null for wrong run, wrong client id, or user-only hydrate', () => {
  const wrongMessages: Message[] = [
    {
      id: 'user-only',
      conversation_id: 'conv-1',
      run_id: 'run-1',
      client_message_id: 'client-msg-1',
      role: 'user',
      content: '问题',
      created_at: '2026-04-27T00:00:00Z',
    },
    {
      id: 'assistant-wrong-run',
      conversation_id: 'conv-1',
      run_id: 'run-2',
      client_message_id: 'client-msg-1',
      role: 'assistant',
      content: '错误 run',
      created_at: '2026-04-27T00:00:01Z',
    },
    {
      id: 'assistant-wrong-client',
      conversation_id: 'conv-1',
      run_id: 'run-1',
      client_message_id: 'client-msg-2',
      role: 'assistant',
      content: '错误 client',
      created_at: '2026-04-27T00:00:02Z',
    },
  ]

  assert.equal(findHydratedAssistantMessage(wrongMessages, {
    conversationId: 'conv-1',
    runId: 'run-1',
    clientMessageId: 'client-msg-1',
  }), null)
})

test('resolveControllerPhaseFromRunStatus maps interrupted to cancelled and success to finalizing', () => {
  const interrupted: ChatRunStatusResponse = {
    run_id: 'run-1',
    status: 'interrupted',
    query: '问题',
    runtime_state: {},
  }
  const success: ChatRunStatusResponse = {
    run_id: 'run-2',
    status: 'success',
    query: '问题',
    runtime_state: {},
  }
  const hitl: ChatRunStatusResponse = {
    run_id: 'run-3',
    status: 'running',
    query: '问题',
    runtime_state: {
      hitl: {
        pending: true,
        kind: 'input',
        prompt: '请补充信息',
        allowed_actions: ['respond'],
      },
    },
  }

  assert.equal(resolveControllerPhaseFromRunStatus(interrupted), 'cancelled')
  assert.equal(resolveControllerPhaseFromRunStatus(success), 'finalizing')
  assert.equal(resolveControllerPhaseFromRunStatus(hitl), 'waiting_hitl')
})

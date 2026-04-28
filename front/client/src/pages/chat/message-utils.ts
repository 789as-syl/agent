import type { ExecutionTraceEntry, Message, MessageContentBlock } from '../../types'
import type { AnswerBasis, PendingUserMessage, StreamingSessionState } from './streaming-session'

export type ProductTraceEvidenceItem = NonNullable<ExecutionTraceEntry['evidence']>[number] & {
  title?: string
  snippet?: string
  source_type?: string
  locator?: string
  evidence_type?: string
}

export type ProductExecutionTraceEntry = ExecutionTraceEntry & {
  answer_basis?: AnswerBasis
  evidence?: ProductTraceEvidenceItem[]
}

export function hydrateMessages(messages: Message[]): Message[] {
  const userIds = new Set(messages.filter((msg) => msg.role === 'user').map((msg) => msg.id))
  return messages.map((message, index) => {
    if (message.role !== 'assistant' || (message.execution_trace && message.execution_trace.length > 0)) {
      return message
    }
    if (message.reply_to_message_id && userIds.has(message.reply_to_message_id)) {
      return message
    }
    const fallbackUser = [...messages.slice(0, index)].reverse().find((item) => item.role === 'user')
    return {
      ...message,
      reply_to_message_id: message.reply_to_message_id || fallbackUser?.id || null,
    }
  })
}

export function buildDisplayMessages(
  messages: Message[],
  params: {
    isRunning: boolean
    streamingContent: string
    executionTrace: ExecutionTraceEntry[]
    conversationId: string
    activeRunId?: string | null
    activeClientMessageId?: string | null
    pendingUserMessage?: PendingUserMessage | null
    session?: StreamingSessionState | null
  }
): Message[] {
  const list = messages.filter((message) => message.conversation_id === params.conversationId)
  const pendingUserMessage = params.pendingUserMessage?.content ? params.pendingUserMessage : null
  const stableClientMessageId =
    params.activeClientMessageId
    || pendingUserMessage?.client_message_id
    || params.session?.pendingUserMessage?.client_message_id
    || null
  const sessionAnswer = sanitizeVisibleText(
    params.session?.finalAnswer || params.session?.assistantContent || params.streamingContent
  )
  const hasPersistedAssistantForPendingUser = Boolean(
    list.some((message) => (
      message.role === 'assistant'
      && (
        matchesClientMessageId(message.client_message_id, stableClientMessageId)
        || (
          message.reply_to_message_id === pendingUserMessage?.id
          && (!params.activeRunId || message.run_id === params.activeRunId)
        )
      )
      && (!params.activeRunId || !stableClientMessageId || message.run_id === params.activeRunId)
    ))
  )
  const shouldShowStreamingAssistant = Boolean(
    sessionAnswer
    || params.executionTrace.length > 0
    || params.session?.contentBlocks?.length
  )

  const hasPersistedUserForPendingMessage = Boolean(
    pendingUserMessage
    && list.some((message) => (
      message.role === 'user'
      && (
        matchesClientMessageId(message.client_message_id, stableClientMessageId)
        || (
          stableClientMessageId
          && message.id === pendingUserMessage.id
        )
        || (
        message.id === pendingUserMessage.id
          || message.content.trim() === pendingUserMessage.content.trim()
        )
      )
    ))
  )

  if (pendingUserMessage && !hasPersistedUserForPendingMessage) {
    list.push({
      id: pendingUserMessage.id,
      conversation_id: params.conversationId,
      role: 'user',
      client_message_id: pendingUserMessage.client_message_id,
      content: pendingUserMessage.content,
      created_at: pendingUserMessage.created_at,
    })
  }

  if (
    shouldShowStreamingAssistant
    && (params.isRunning || Boolean(pendingUserMessage) || Boolean(sessionAnswer))
    && !hasPersistedAssistantForPendingUser
  ) {
    list.push({
      id: 'streaming-assistant',
      conversation_id: params.conversationId,
      client_message_id: stableClientMessageId,
      run_id: params.activeRunId,
      role: 'assistant',
      content: sessionAnswer,
      content_blocks: sanitizeContentBlocks(params.session?.contentBlocks ?? null),
      execution_trace: sanitizeExecutionTrace(params.executionTrace),
      created_at: new Date().toISOString(),
    })
  }
  return list
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isToolProtocolBlock(block: unknown): boolean {
  if (!isRecord(block)) return false
  return (
    typeof block.tool === 'string' ||
    typeof block.protocol_version === 'string' ||
    typeof block.retrieval_failed === 'boolean' ||
    'payload' in block ||
    'evidence_blocks' in block
  )
}

export function resolveRenderableContent(message: Message, isRunning: boolean): string {
  const safeContent = sanitizeVisibleText(message.content)
  if (safeContent && safeContent.trim()) {
    return safeContent
  }

  const blocks = sanitizeContentBlocks(message.content_blocks) ?? []
  if (blocks.length > 0) {
    const text = blocks
      .map((block) => {
        if (isToolProtocolBlock(block)) {
          return ''
        }
        return typeof block.text === 'string' && block.text.trim() ? block.text : ''
      })
      .filter((item) => item.trim().length > 0)
      .join('\n\n')
    if (text.trim()) return text
  }

  return isRunning ? '正在生成回答...' : ''
}


const TOOL_PROTOCOL_MARKERS = [
  '"success"',
  '"tool"',
  '"payload"',
  '"protocol_version"',
  '"protocol_path"',
  '"retrieval_failed"',
  '"error_code"',
  'knowledge_retrieval',
]

function containsToolProtocolMarker(value: string): boolean {
  return TOOL_PROTOCOL_MARKERS.some((marker) => value.includes(marker))
}

function stripBalancedToolJsonPrefix(value: string): string {
  const trimmedStart = value.trimStart()
  if (!trimmedStart.startsWith('{')) return value

  let depth = 0
  let inString = false
  let escaped = false
  for (let index = 0; index < trimmedStart.length; index += 1) {
    const char = trimmedStart[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') inString = true
    else if (char === '{') depth += 1
    else if (char === '}') {
      depth -= 1
      if (depth === 0) {
        const candidate = trimmedStart.slice(0, index + 1)
        if (containsToolProtocolMarker(candidate)) {
          return trimmedStart.slice(index + 1).trimStart()
        }
        return value
      }
    }
  }

  return containsToolProtocolMarker(trimmedStart) ? '' : value
}

export function sanitizeVisibleText(value: unknown): string {
  if (typeof value !== 'string') return ''
  let text = stripBalancedToolJsonPrefix(value)
  text = text
    .split(/\r?\n/)
    .filter((line) => !containsToolProtocolMarker(line) || !line.trim().startsWith('{'))
    .join('\n')
  return text.trimStart()
}

export function sanitizeContentBlocks(blocks: MessageContentBlock[] | null | undefined): MessageContentBlock[] | null {
  if (!Array.isArray(blocks)) return null
  const sanitized = blocks
    .filter((block) => !isToolProtocolBlock(block))
    .map((block) => {
      if (typeof block.text !== 'string') return block
      return { ...block, text: sanitizeVisibleText(block.text) }
    })
    .filter((block) => typeof block.text !== 'string' || block.text.trim().length > 0)
  return sanitized.length > 0 ? sanitized : null
}

export function sanitizeExecutionTrace(trace: ExecutionTraceEntry[] | null | undefined): ExecutionTraceEntry[] {
  if (!Array.isArray(trace)) return []
  return trace.map((entry) => ({
    ...entry,
    title: sanitizeVisibleText(entry.title) || entry.title,
    detail: sanitizeVisibleText(entry.detail),
    metadata: undefined,
    evidence: entry.evidence?.map((item) => ({
      ...item,
      detail: sanitizeVisibleText(item.detail),
      title: sanitizeVisibleText((item as ProductTraceEvidenceItem).title),
      snippet: sanitizeVisibleText((item as ProductTraceEvidenceItem).snippet),
      source_type: sanitizeVisibleText((item as ProductTraceEvidenceItem).source_type),
      locator: sanitizeVisibleText((item as ProductTraceEvidenceItem).locator),
      evidence_type: sanitizeVisibleText((item as ProductTraceEvidenceItem).evidence_type),
    })),
  }))
}

function matchesClientMessageId(
  messageClientMessageId: string | null | undefined,
  activeClientMessageId: string | null | undefined,
): boolean {
  return Boolean(
    messageClientMessageId
    && activeClientMessageId
    && messageClientMessageId === activeClientMessageId
  )
}

export function getTraceAnswerBasis(trace: ExecutionTraceEntry[] | null | undefined): AnswerBasis | null {
  if (!Array.isArray(trace)) return null
  for (const entry of [...trace].reverse()) {
    const basis = (entry as ProductExecutionTraceEntry).answer_basis
    if (isAnswerBasis(basis)) {
      return basis
    }
  }

  if (trace.some((entry) => entry.decision_code === 'direct_answer')) {
    return 'direct'
  }
  if (trace.some((entry) => entry.kind === 'clarification' || entry.decision_code === 'clarify_missing_context')) {
    return 'needs_clarification'
  }
  if (trace.some((entry) => entry.decision_code === 'retrieval_failed' || /检索失败|检索暂不可用/i.test(`${entry.title} ${entry.detail || ''}`))) {
    return 'retrieval_unavailable'
  }
  if (trace.some((entry) => entry.decision_code === 'retrieval_insufficient' || /证据不足|insufficient/i.test(`${entry.title} ${entry.detail || ''}`))) {
    return 'evidence_insufficient'
  }
  if (trace.some((entry) => entry.decision_code === 'retrieval_hit' || /已检索到 .*知识库证据|知识库证据回答/i.test(`${entry.title} ${entry.detail || ''}`))) {
    return 'knowledge_backed'
  }
  return null
}

function isAnswerBasis(value: unknown): value is AnswerBasis {
  return (
    value === 'knowledge_backed'
    || value === 'direct'
    || value === 'retrieval_unavailable'
    || value === 'evidence_insufficient'
    || value === 'needs_clarification'
  )
}

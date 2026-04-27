"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.hydrateMessages = hydrateMessages;
exports.buildDisplayMessages = buildDisplayMessages;
function hydrateMessages(messages) {
    const userIds = new Set(messages.filter((msg) => msg.role === 'user').map((msg) => msg.id));
    return messages.map((message, index) => {
        if (message.role !== 'assistant' || (message.execution_trace && message.execution_trace.length > 0)) {
            return message;
        }
        if (message.reply_to_message_id && userIds.has(message.reply_to_message_id)) {
            return message;
        }
        const fallbackUser = [...messages.slice(0, index)].reverse().find((item) => item.role === 'user');
        return {
            ...message,
            reply_to_message_id: message.reply_to_message_id || fallbackUser?.id || null,
        };
    });
}
function buildDisplayMessages(messages, params) {
    const list = [...messages];
    const pendingUserMessage = params.pendingUserMessage;
    if (pendingUserMessage && !list.some((message) => message.id === pendingUserMessage.id)) {
        list.push({
            id: pendingUserMessage.id,
            conversation_id: params.conversationId,
            role: 'user',
            content: pendingUserMessage.content,
            created_at: pendingUserMessage.created_at,
        });
    }
    if ((params.isRunning || Boolean(pendingUserMessage))
        && (params.streamingContent || params.executionTrace.length > 0 || Boolean(params.session?.rawReasoning))) {
        list.push({
            id: 'streaming-assistant',
            conversation_id: params.conversationId,
            role: 'assistant',
            content: params.streamingContent,
            raw_reasoning: params.session?.rawReasoning ?? null,
            content_blocks: params.session?.contentBlocks ?? null,
            execution_trace: params.executionTrace,
            created_at: new Date().toISOString(),
        });
    }
    return list;
}

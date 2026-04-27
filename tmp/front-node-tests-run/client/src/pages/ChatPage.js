"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.default = ChatPage;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const react_router_dom_1 = require("react-router-dom");
const lucide_react_1 = require("lucide-react");
const sonner_1 = require("sonner");
const api_1 = require("../api");
const store_1 = require("../store");
const message_utils_1 = require("./chat/message-utils");
const session_persistence_1 = require("./chat/session-persistence");
const ChatComposer_1 = require("./chat/components/ChatComposer");
const ChatEmptyState_1 = require("./chat/components/ChatEmptyState");
const ChatMessageList_1 = require("./chat/components/ChatMessageList");
const streaming_session_1 = require("./chat/streaming-session");
const SUGGESTED_PROMPTS = [
    '请总结机器学习和深度学习的区别',
    '帮我根据题库生成 5 道测试题',
    '列出最近一周检索命中率变化原因',
    '解释这段知识点的核心概念',
];
function buildPendingUserMessage(content) {
    return {
        id: `pending-user-${Date.now()}`,
        content,
        created_at: new Date().toISOString(),
    };
}
function resolvePendingUserMessage(query, existing) {
    if (existing)
        return existing;
    const normalized = query?.trim();
    if (!normalized)
        return null;
    return buildPendingUserMessage(normalized);
}
function isActiveRunStatus(status) {
    return status === 'pending' || status === 'running';
}
const PLAYBACK_REPLAY_INTERVAL_MS = 16;
const PLAYBACK_REPLAY_BATCH_SIZE = 4;
function ChatPage() {
    const { id } = (0, react_router_dom_1.useParams)();
    const navigate = (0, react_router_dom_1.useNavigate)();
    const messagesEndRef = (0, react_1.useRef)(null);
    const textareaRef = (0, react_1.useRef)(null);
    const snapshotPersistTimerRef = (0, react_1.useRef)(null);
    const [input, setInput] = (0, react_1.useState)('');
    const [hitlInput, setHitlInput] = (0, react_1.useState)('');
    const [submittingHitl, setSubmittingHitl] = (0, react_1.useState)(false);
    const [snapshotRunId, setSnapshotRunId] = (0, react_1.useState)(null);
    const [snapshotLastEventId, setSnapshotLastEventId] = (0, react_1.useState)(null);
    const messages = (0, store_1.useConversationStore)((state) => state.messages);
    const fetchMessages = (0, store_1.useConversationStore)((state) => state.fetchMessages);
    const addMessage = (0, store_1.useConversationStore)((state) => state.addMessage);
    const createConversation = (0, store_1.useConversationStore)((state) => state.createConversation);
    const { currentRunId, isRunning, setCurrentRunId, setIsRunning, clearChat, } = (0, store_1.useChatStore)();
    const [streamingSession, setStreamingSession] = (0, react_1.useState)((0, streaming_session_1.createStreamingSessionState)());
    const streamingSessionRef = (0, react_1.useRef)((0, streaming_session_1.createStreamingSessionState)());
    const terminalResolutionRunRef = (0, react_1.useRef)(null);
    const replayTimerRef = (0, react_1.useRef)(null);
    const replayResolverRef = (0, react_1.useRef)(null);
    const [isReplaying, setIsReplaying] = (0, react_1.useState)(false);
    const updateStreamingSession = (0, react_1.useCallback)((updater) => {
        const nextState = updater(streamingSessionRef.current);
        streamingSessionRef.current = nextState;
        setStreamingSession(nextState);
        return nextState;
    }, []);
    const replaceStreamingSession = (0, react_1.useCallback)((nextState) => {
        streamingSessionRef.current = nextState;
        setStreamingSession(nextState);
    }, []);
    const resetStreamingSession = (0, react_1.useCallback)((pendingUserMessage = null) => {
        replaceStreamingSession((0, streaming_session_1.createStreamingSessionState)(pendingUserMessage));
    }, [replaceStreamingSession]);
    const persistChatRunSnapshot = (0, react_1.useCallback)((conversationId, runId, sessionState, lastEventId) => {
        const resolvedLastEventId = lastEventId ?? api_1.sseClient.getLastEventId() ?? null;
        setSnapshotRunId(runId);
        setSnapshotLastEventId(resolvedLastEventId);
        (0, session_persistence_1.saveChatRunSnapshot)({
            conversationId,
            runId,
            lastEventId: resolvedLastEventId,
            session: sessionState,
        });
    }, []);
    const stopPlaybackReplay = (0, react_1.useCallback)(() => {
        if (replayTimerRef.current) {
            window.clearTimeout(replayTimerRef.current);
            replayTimerRef.current = null;
        }
        if (replayResolverRef.current) {
            const resolve = replayResolverRef.current;
            replayResolverRef.current = null;
            resolve(streamingSessionRef.current);
        }
        setIsReplaying(false);
    }, []);
    const stopStreamingRun = (0, react_1.useCallback)((options = {}) => {
        const { clearSession = false, clearSnapshotRunId = false } = options;
        stopPlaybackReplay();
        api_1.sseClient.disconnect();
        setIsRunning(false);
        setCurrentRunId(null);
        if (clearSnapshotRunId) {
            setSnapshotRunId(null);
            setSnapshotLastEventId(null);
        }
        if (clearSession) {
            resetStreamingSession();
        }
    }, [resetStreamingSession, setCurrentRunId, setIsRunning, stopPlaybackReplay]);
    const replayPlaybackEventsIncrementally = (0, react_1.useCallback)((baseState, events) => {
        stopPlaybackReplay();
        replaceStreamingSession(baseState);
        if (events.length === 0) {
            return Promise.resolve(baseState);
        }
        return new Promise((resolve) => {
            let eventIndex = 0;
            setIsReplaying(true);
            replayResolverRef.current = resolve;
            const finishReplay = (finalState) => {
                if (replayTimerRef.current) {
                    window.clearTimeout(replayTimerRef.current);
                    replayTimerRef.current = null;
                }
                replayResolverRef.current = null;
                setIsReplaying(false);
                resolve(finalState);
            };
            const tick = () => {
                const batch = events.slice(eventIndex, eventIndex + PLAYBACK_REPLAY_BATCH_SIZE);
                if (batch.length === 0) {
                    finishReplay(streamingSessionRef.current);
                    return;
                }
                const nextState = (0, streaming_session_1.playbackStreamingEvents)(streamingSessionRef.current, batch);
                replaceStreamingSession(nextState);
                eventIndex += batch.length;
                if (eventIndex >= events.length) {
                    finishReplay(nextState);
                    return;
                }
                replayTimerRef.current = window.setTimeout(tick, PLAYBACK_REPLAY_INTERVAL_MS);
            };
            tick();
        });
    }, [replaceStreamingSession, stopPlaybackReplay]);
    const restoreSessionFromPlayback = (0, react_1.useCallback)(async (fallbackUserMessage, runtimeState, existingState, playback) => {
        const baseState = (0, streaming_session_1.restoreStreamingSessionFromRun)(fallbackUserMessage, runtimeState, playback.mode === 'full' ? null : existingState, playback.mode === 'full' ? [] : playback.events);
        if (playback.mode === 'full' && playback.events.length > 0) {
            return replayPlaybackEventsIncrementally(baseState, playback.events);
        }
        replaceStreamingSession(baseState);
        return baseState;
    }, [replaceStreamingSession, replayPlaybackEventsIncrementally]);
    const fetchMessagesSafely = (0, react_1.useCallback)(async (conversationId) => {
        try {
            await fetchMessages(conversationId);
            return true;
        }
        catch {
            return false;
        }
    }, [fetchMessages]);
    const loadPlaybackEvents = (0, react_1.useCallback)(async (conversationId, run, afterEventId) => {
        const fetchFullPlayback = async () => {
            try {
                const playback = await api_1.chatRunsApi.listEvents(conversationId, run.run_id);
                return {
                    events: playback.events,
                    mode: playback.events.length > 0 ? 'full' : 'none',
                    lastEventId: playback.last_event_id ?? null,
                };
            }
            catch {
                return {
                    events: [],
                    mode: 'none',
                    lastEventId: afterEventId ?? null,
                };
            }
        };
        if (afterEventId) {
            try {
                const playback = await api_1.chatRunsApi.listEvents(conversationId, run.run_id, { after_event_id: afterEventId });
                if (playback.anchor_found) {
                    return {
                        events: playback.events,
                        mode: 'delta',
                        lastEventId: playback.last_event_id ?? afterEventId ?? null,
                    };
                }
            }
            catch {
                // Fall back to full playback recovery.
            }
        }
        return fetchFullPlayback();
    }, []);
    const backfillPlaybackGap = (0, react_1.useCallback)(async (conversationId, runId) => {
        const anchorEventId = api_1.sseClient.getLastEventId();
        if (!anchorEventId) {
            return;
        }
        try {
            const playback = await api_1.chatRunsApi.listEvents(conversationId, runId, { after_event_id: anchorEventId });
            if (playback.last_event_id) {
                api_1.sseClient.setLastEventId(playback.last_event_id);
            }
            if (!playback.anchor_found) {
                const run = await api_1.chatRunsApi.get(conversationId, runId);
                const fullPlayback = await loadPlaybackEvents(conversationId, run, anchorEventId);
                const restoredSession = await restoreSessionFromPlayback(resolvePendingUserMessage(run.query, streamingSessionRef.current.pendingUserMessage), run.runtime_state, fullPlayback.mode === 'full' ? null : streamingSessionRef.current, fullPlayback);
                persistChatRunSnapshot(conversationId, runId, restoredSession, fullPlayback.lastEventId);
                return;
            }
            if (playback.events.length === 0) {
                return;
            }
            const nextSession = (0, streaming_session_1.playbackStreamingEvents)(streamingSessionRef.current, playback.events);
            replaceStreamingSession(nextSession);
            persistChatRunSnapshot(conversationId, runId, nextSession, playback.last_event_id ?? anchorEventId);
        }
        catch {
            // Ignore backfill failures; terminal recovery path still reloads from persisted playback.
        }
    }, [loadPlaybackEvents, persistChatRunSnapshot, restoreSessionFromPlayback]);
    const reconcileCompletedRun = (0, react_1.useCallback)(async (conversationId, runId, sessionState) => {
        if (terminalResolutionRunRef.current === runId) {
            return;
        }
        terminalResolutionRunRef.current = runId;
        persistChatRunSnapshot(conversationId, runId, sessionState);
        stopStreamingRun();
        const fetched = await fetchMessagesSafely(conversationId);
        if (!fetched) {
            return;
        }
        (0, session_persistence_1.clearChatRunSnapshot)(conversationId);
        setSnapshotRunId(null);
        setSnapshotLastEventId(null);
        stopStreamingRun({ clearSession: true, clearSnapshotRunId: true });
    }, [fetchMessagesSafely, persistChatRunSnapshot, stopStreamingRun]);
    const handleTerminalStreamError = (0, react_1.useCallback)(async (conversationId, runId, fallbackMessage) => {
        if (terminalResolutionRunRef.current === runId) {
            return;
        }
        try {
            const run = await api_1.chatRunsApi.get(conversationId, runId);
            const playback = await loadPlaybackEvents(conversationId, run, api_1.sseClient.getLastEventId() ?? null);
            if (playback.lastEventId) {
                api_1.sseClient.setLastEventId(playback.lastEventId);
            }
            const restoredSession = await restoreSessionFromPlayback(resolvePendingUserMessage(run.query, streamingSessionRef.current.pendingUserMessage), run.runtime_state, playback.mode === 'full' ? null : streamingSessionRef.current, playback);
            if (run.status === 'success') {
                await reconcileCompletedRun(conversationId, run.run_id, restoredSession);
                return;
            }
            terminalResolutionRunRef.current = runId;
            persistChatRunSnapshot(conversationId, run.run_id, restoredSession, playback.lastEventId);
            stopStreamingRun();
            if (run.runtime_state?.hitl?.pending) {
                sonner_1.toast.success('运行等待人工确认，已恢复到 HITL 状态');
                return;
            }
            if (run.status === 'interrupted') {
                sonner_1.toast.success('回答已中断，过程已保留，可点击继续');
                return;
            }
            if (run.status === 'failed') {
                sonner_1.toast.error(run.error_message || fallbackMessage || '本次回答失败，可点击继续');
                return;
            }
            if (isActiveRunStatus(run.status)) {
                sonner_1.toast.error('连接中断，过程已保留，可点击继续恢复当前运行');
                return;
            }
        }
        catch {
            terminalResolutionRunRef.current = runId;
            persistChatRunSnapshot(conversationId, runId, streamingSessionRef.current);
            stopStreamingRun();
            sonner_1.toast.error('连接中断，过程已保留，可点击继续恢复');
            return;
        }
        terminalResolutionRunRef.current = runId;
        persistChatRunSnapshot(conversationId, runId, streamingSessionRef.current);
        stopStreamingRun();
        sonner_1.toast.error(fallbackMessage || '连接中断，请重试');
    }, [loadPlaybackEvents, persistChatRunSnapshot, reconcileCompletedRun, restoreSessionFromPlayback, stopStreamingRun]);
    const connectToRun = (0, react_1.useCallback)((conversationId, runId, lastEventId) => {
        let hasOpenedOnce = false;
        api_1.sseClient.disconnect();
        api_1.sseClient.onOpen(() => {
            if (!hasOpenedOnce) {
                hasOpenedOnce = true;
                if (lastEventId) {
                    void backfillPlaybackGap(conversationId, runId);
                }
                return;
            }
            void backfillPlaybackGap(conversationId, runId);
        });
        api_1.sseClient.setReconnectGuard(async (guardConversationId, guardRunId) => {
            try {
                const run = await api_1.chatRunsApi.get(guardConversationId, guardRunId);
                const shouldReconnect = isActiveRunStatus(run.status) && !run.runtime_state?.hitl?.pending;
                if (!shouldReconnect) {
                    await handleTerminalStreamError(guardConversationId, guardRunId, '当前运行已结束');
                }
                return shouldReconnect;
            }
            catch {
                return false;
            }
        });
        api_1.sseClient.onEvent((event) => {
            updateStreamingSession((current) => (0, streaming_session_1.applyStreamingEvent)(current, event));
            switch (event.event_type) {
                case 'done': {
                    stopStreamingRun();
                    const completedSession = streamingSessionRef.current;
                    void reconcileCompletedRun(conversationId, runId, completedSession);
                    break;
                }
                case 'error': {
                    stopStreamingRun();
                    void handleTerminalStreamError(conversationId, runId, event.trace_data?.error_message || '处理请求时出现错误');
                    break;
                }
                case 'hitl_requested': {
                    persistChatRunSnapshot(conversationId, runId, streamingSessionRef.current);
                    stopStreamingRun();
                    break;
                }
                default:
                    break;
            }
        });
        api_1.sseClient.onError(() => {
            void handleTerminalStreamError(conversationId, runId, '连接中断，请重试');
        });
        api_1.sseClient.connect(conversationId, runId, lastEventId);
    }, [
        backfillPlaybackGap,
        handleTerminalStreamError,
        persistChatRunSnapshot,
        reconcileCompletedRun,
        stopStreamingRun,
        updateStreamingSession,
    ]);
    const startStreamForRun = (0, react_1.useCallback)((conversationId, runId, sessionState, lastEventId) => {
        stopPlaybackReplay();
        terminalResolutionRunRef.current = null;
        const nextSession = (0, streaming_session_1.restoreStreamingSessionFromRun)(sessionState.pendingUserMessage, undefined, sessionState);
        replaceStreamingSession(nextSession);
        setCurrentRunId(runId);
        setIsRunning(true);
        persistChatRunSnapshot(conversationId, runId, nextSession, lastEventId);
        connectToRun(conversationId, runId, lastEventId);
    }, [connectToRun, persistChatRunSnapshot, replaceStreamingSession, setCurrentRunId, setIsRunning, stopPlaybackReplay]);
    const resumeChatRun = (0, react_1.useCallback)(async (conversationId, run, snapshotSession, snapshotLastEventId) => {
        const fallbackUserMessage = resolvePendingUserMessage(run.query, snapshotSession?.pendingUserMessage);
        const playback = await loadPlaybackEvents(conversationId, run, snapshotLastEventId);
        if (playback.lastEventId) {
            api_1.sseClient.setLastEventId(playback.lastEventId);
        }
        const restoredSession = await restoreSessionFromPlayback(fallbackUserMessage, run.runtime_state, playback.mode === 'full' ? null : snapshotSession, playback);
        persistChatRunSnapshot(conversationId, run.run_id, restoredSession, playback.lastEventId ?? snapshotLastEventId);
        if (!isActiveRunStatus(run.status)) {
            if (run.status === 'success') {
                await reconcileCompletedRun(conversationId, run.run_id, restoredSession);
                return;
            }
            stopStreamingRun();
            return;
        }
        if (run.runtime_state?.hitl?.pending) {
            stopStreamingRun();
            return;
        }
        startStreamForRun(conversationId, run.run_id, restoredSession, playback.lastEventId ?? snapshotLastEventId);
    }, [
        loadPlaybackEvents,
        persistChatRunSnapshot,
        reconcileCompletedRun,
        restoreSessionFromPlayback,
        startStreamForRun,
        stopStreamingRun,
    ]);
    (0, react_1.useEffect)(() => {
        let cancelled = false;
        api_1.sseClient.disconnect();
        clearChat();
        setSnapshotRunId(null);
        setSnapshotLastEventId(null);
        terminalResolutionRunRef.current = null;
        resetStreamingSession();
        const initialize = async () => {
            if (!id || id === '')
                return;
            await fetchMessagesSafely(id);
            if (cancelled)
                return;
            const snapshot = (0, session_persistence_1.loadChatRunSnapshot)(id);
            if (!snapshot)
                return;
            if (!snapshot.runId) {
                setSnapshotRunId(null);
                setSnapshotLastEventId(snapshot.lastEventId ?? null);
                replaceStreamingSession(snapshot.session);
                return;
            }
            try {
                const run = await api_1.chatRunsApi.get(id, snapshot.runId);
                if (cancelled)
                    return;
                await resumeChatRun(id, run, snapshot.session, snapshot.lastEventId);
            }
            catch {
                (0, session_persistence_1.clearChatRunSnapshot)(id);
                setSnapshotRunId(null);
                setSnapshotLastEventId(null);
                resetStreamingSession();
            }
        };
        void initialize();
        return () => {
            cancelled = true;
            stopPlaybackReplay();
            api_1.sseClient.setReconnectGuard(undefined);
            api_1.sseClient.disconnect();
        };
    }, [clearChat, fetchMessagesSafely, id, replaceStreamingSession, resetStreamingSession, resumeChatRun, stopPlaybackReplay]);
    (0, react_1.useEffect)(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: isRunning || isReplaying ? 'auto' : 'smooth' });
    }, [isReplaying, isRunning, messages, streamingSession.assistantContent, streamingSession.executionTrace, streamingSession.hitl]);
    (0, react_1.useEffect)(() => {
        const el = textareaRef.current;
        if (!el)
            return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }, [input]);
    (0, react_1.useEffect)(() => {
        if (!id || id === '')
            return;
        const hasSnapshotPayload = Boolean(snapshotRunId ||
            currentRunId ||
            isRunning ||
            streamingSession.pendingUserMessage ||
            streamingSession.executionTrace.length > 0 ||
            streamingSession.assistantContent ||
            streamingSession.rawReasoning ||
            streamingSession.finalAnswer ||
            streamingSession.hitl?.pending);
        if (!hasSnapshotPayload)
            return;
        if (snapshotPersistTimerRef.current) {
            window.clearTimeout(snapshotPersistTimerRef.current);
        }
        snapshotPersistTimerRef.current = window.setTimeout(() => {
            (0, session_persistence_1.saveChatRunSnapshot)({
                conversationId: id,
                runId: snapshotRunId ?? currentRunId,
                lastEventId: api_1.sseClient.getLastEventId() ?? null,
                session: streamingSessionRef.current,
            });
            snapshotPersistTimerRef.current = null;
        }, isRunning || isReplaying ? 150 : 0);
        return () => {
            if (snapshotPersistTimerRef.current) {
                window.clearTimeout(snapshotPersistTimerRef.current);
                snapshotPersistTimerRef.current = null;
            }
        };
    }, [currentRunId, id, isReplaying, isRunning, snapshotRunId, streamingSession]);
    const handleSendMessage = async () => {
        if (!input.trim() || isRunning || isReplaying)
            return;
        const query = input.trim();
        stopPlaybackReplay();
        setInput('');
        setHitlInput('');
        clearChat();
        setSnapshotRunId(null);
        setSnapshotLastEventId(null);
        api_1.sseClient.resetLastEventId();
        let conversationId = id;
        if (!conversationId || conversationId === '') {
            try {
                const conversation = await createConversation(query.slice(0, 30));
                conversationId = conversation.id;
                navigate(`/${conversationId}`);
            }
            catch {
                sonner_1.toast.error('创建会话失败');
                return;
            }
        }
        const pendingUserMessage = buildPendingUserMessage(query);
        addMessage({
            id: pendingUserMessage.id,
            conversation_id: conversationId,
            role: 'user',
            content: query,
            created_at: pendingUserMessage.created_at,
        });
        const nextSession = (0, streaming_session_1.createStreamingSessionState)(pendingUserMessage);
        replaceStreamingSession(nextSession);
        persistChatRunSnapshot(conversationId, null, nextSession);
        try {
            const run = await api_1.chatRunsApi.create(conversationId, { query });
            startStreamForRun(conversationId, run.run_id, nextSession);
        }
        catch {
            (0, session_persistence_1.clearChatRunSnapshot)(conversationId);
            setSnapshotRunId(null);
            setSnapshotLastEventId(null);
            stopStreamingRun({ clearSession: true, clearSnapshotRunId: true });
            sonner_1.toast.error('发送消息失败');
        }
    };
    const handleInterrupt = async () => {
        if (!currentRunId || !id)
            return;
        try {
            await api_1.chatRunsApi.interrupt(id, currentRunId);
            persistChatRunSnapshot(id, currentRunId, streamingSessionRef.current);
            stopStreamingRun();
            sonner_1.toast.success('已中断当前回答，过程已保留，可点击继续');
        }
        catch {
            sonner_1.toast.error('中断失败');
        }
    };
    const handleRetry = async () => {
        if (!id || isRunning || isReplaying)
            return;
        const sourceRunId = snapshotRunId ?? (0, session_persistence_1.loadChatRunSnapshot)(id)?.runId ?? null;
        if (sourceRunId) {
            try {
                const sourceRun = await api_1.chatRunsApi.get(id, sourceRunId);
                const pendingUserMessage = resolvePendingUserMessage(sourceRun.query, streamingSessionRef.current.pendingUserMessage);
                if (isActiveRunStatus(sourceRun.status)) {
                    const playback = await loadPlaybackEvents(id, sourceRun, snapshotLastEventId);
                    if (playback.lastEventId) {
                        api_1.sseClient.setLastEventId(playback.lastEventId);
                    }
                    const restoredSession = (0, streaming_session_1.restoreStreamingSessionFromRun)(pendingUserMessage, sourceRun.runtime_state, playback.mode === 'full' ? null : streamingSessionRef.current, playback.events);
                    replaceStreamingSession(restoredSession);
                    if (sourceRun.runtime_state?.hitl?.pending) {
                        stopStreamingRun();
                        sonner_1.toast.success('当前运行等待人工确认，请先提交 HITL 决策');
                        return;
                    }
                    startStreamForRun(id, sourceRun.run_id, restoredSession, playback.lastEventId ?? snapshotLastEventId);
                    sonner_1.toast.success('已恢复当前运行');
                    return;
                }
                if (sourceRun.status === 'failed' ||
                    sourceRun.status === 'interrupted' ||
                    sourceRun.status === 'success') {
                    const nextSession = (0, streaming_session_1.createStreamingSessionState)(pendingUserMessage);
                    replaceStreamingSession(nextSession);
                    const nextRun = sourceRun.status === 'failed' || sourceRun.status === 'interrupted'
                        ? await api_1.chatRunsApi.retry(id, sourceRunId)
                        : await api_1.chatRunsApi.regenerate(id, sourceRunId);
                    startStreamForRun(id, nextRun.run_id, nextSession);
                    return;
                }
            }
            catch {
                // Fall through to message-backed regenerate / input retry.
            }
        }
        const lastAssistantMessage = [...messages].reverse().find((message) => (message.role === 'assistant' &&
            Boolean(message.run_id)));
        if (lastAssistantMessage?.run_id) {
            const started = await handleRegenerate(lastAssistantMessage);
            if (started) {
                return;
            }
        }
        const lastUserMessage = [...messages].reverse().find((message) => message.role === 'user');
        if (!lastUserMessage)
            return;
        setInput(lastUserMessage.content);
    };
    const resolveSeedMessageForAssistant = (0, react_1.useCallback)((assistantMessage) => {
        const pairedUserMessage = assistantMessage.reply_to_message_id
            ? messages.find((message) => message.id === assistantMessage.reply_to_message_id)
            : [...messages]
                .slice(0, Math.max(0, messages.findIndex((message) => message.id === assistantMessage.id)))
                .reverse()
                .find((message) => message.role === 'user');
        return resolvePendingUserMessage(pairedUserMessage?.content || '');
    }, [messages]);
    const handleRegenerate = (0, react_1.useCallback)(async (assistantMessage) => {
        if (!id || isRunning || isReplaying || !assistantMessage.run_id)
            return false;
        const pendingUserMessage = resolveSeedMessageForAssistant(assistantMessage);
        if (!pendingUserMessage) {
            sonner_1.toast.error('缺少可用于重新生成的原始问题');
            return false;
        }
        try {
            const nextSession = (0, streaming_session_1.createStreamingSessionState)(pendingUserMessage);
            replaceStreamingSession(nextSession);
            const nextRun = await api_1.chatRunsApi.regenerate(id, assistantMessage.run_id);
            startStreamForRun(id, nextRun.run_id, nextSession);
            return true;
        }
        catch {
            sonner_1.toast.error('重新生成失败');
            return false;
        }
    }, [id, isReplaying, isRunning, replaceStreamingSession, resolveSeedMessageForAssistant, startStreamForRun]);
    const submitHitlDecision = (0, react_1.useCallback)(async (type) => {
        if (!id || !snapshotRunId || submittingHitl)
            return;
        const requiresText = type === 'respond' || type === 'edit';
        if (requiresText && !hitlInput.trim()) {
            sonner_1.toast.error('请先输入需要提交的内容');
            return;
        }
        const decisionValue = requiresText ? hitlInput.trim() : null;
        setSubmittingHitl(true);
        try {
            await api_1.chatRunsApi.resume(id, snapshotRunId, {
                decision: {
                    type,
                    value: decisionValue,
                },
            });
            setHitlInput('');
            const run = await api_1.chatRunsApi.get(id, snapshotRunId);
            const restoredSession = (0, streaming_session_1.restoreStreamingSessionFromRun)(resolvePendingUserMessage(run.query, streamingSessionRef.current.pendingUserMessage), run.runtime_state, streamingSessionRef.current);
            replaceStreamingSession(restoredSession);
            persistChatRunSnapshot(id, snapshotRunId, restoredSession);
            if (isActiveRunStatus(run.status) && !run.runtime_state?.hitl?.pending) {
                startStreamForRun(id, snapshotRunId, restoredSession, api_1.sseClient.getLastEventId());
            }
            sonner_1.toast.success('HITL 决策已提交');
        }
        catch {
            sonner_1.toast.error('提交 HITL 决策失败');
        }
        finally {
            setSubmittingHitl(false);
        }
    }, [hitlInput, id, persistChatRunSnapshot, replaceStreamingSession, snapshotRunId, startStreamForRun, submittingHitl]);
    const hydratedMessages = (0, react_1.useMemo)(() => (0, message_utils_1.hydrateMessages)(messages), [messages]);
    const displayMessages = (0, react_1.useMemo)(() => (0, message_utils_1.buildDisplayMessages)(hydratedMessages, {
        isRunning,
        streamingContent: streamingSession.assistantContent,
        executionTrace: streamingSession.executionTrace,
        conversationId: id || '',
        pendingUserMessage: streamingSession.pendingUserMessage,
        session: streamingSession,
    }), [
        hydratedMessages,
        id,
        isRunning,
        streamingSession,
    ]);
    const composerStatusText = (0, react_1.useMemo)(() => {
        if (streamingSession.hitl?.pending)
            return '运行等待人工确认，请先提交 HITL 决策';
        if (isRunning)
            return '模型正在生成回答...';
        if (isReplaying)
            return '正在恢复执行过程...';
        if (snapshotRunId)
            return '已保留运行状态，可继续 / 重试 / 重新生成';
        return '支持 Markdown、表格与代码块';
    }, [isReplaying, isRunning, snapshotRunId, streamingSession.hitl?.pending]);
    const hitlActions = streamingSession.hitl?.allowed_actions || [];
    return ((0, jsx_runtime_1.jsx)("div", { className: "flex h-full bg-slate-100", children: (0, jsx_runtime_1.jsxs)("div", { className: "flex min-w-0 flex-1 flex-col", children: [(0, jsx_runtime_1.jsx)("div", { className: "flex items-center justify-between border-b border-slate-200/80 bg-white/80 px-4 py-3 backdrop-blur lg:px-6", children: (0, jsx_runtime_1.jsxs)("div", { className: "flex items-center gap-2 text-xs font-medium text-slate-500", children: [(0, jsx_runtime_1.jsx)(lucide_react_1.Wand2, { className: "h-4 w-4 text-indigo-500" }), "AI \u77E5\u8BC6\u68C0\u7D22\u5DF2\u542F\u7528"] }) }), streamingSession.hitl?.pending && snapshotRunId && id && ((0, jsx_runtime_1.jsx)("div", { className: "border-b border-cyan-200 bg-cyan-50/80 px-4 py-3 text-xs text-cyan-900 lg:px-6", children: (0, jsx_runtime_1.jsxs)("div", { className: "mx-auto flex max-w-4xl flex-col gap-3", children: [(0, jsx_runtime_1.jsxs)("div", { children: [(0, jsx_runtime_1.jsx)("p", { className: "text-sm font-semibold", children: "HITL \u5F85\u5904\u7406" }), (0, jsx_runtime_1.jsx)("p", { className: "mt-1 whitespace-pre-wrap text-xs leading-6", children: streamingSession.hitl.prompt || '请补充必要信息后继续。' })] }), (hitlActions.includes('respond') || hitlActions.includes('edit')) && ((0, jsx_runtime_1.jsx)("textarea", { value: hitlInput, onChange: (event) => setHitlInput(event.target.value), placeholder: hitlActions.includes('edit') ? '输入编辑后的内容…' : '输入补充说明…', className: "min-h-[80px] rounded-xl border border-cyan-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-cyan-400" })), (0, jsx_runtime_1.jsxs)("div", { className: "flex flex-wrap items-center gap-2", children: [hitlActions.includes('respond') && ((0, jsx_runtime_1.jsx)("button", { onClick: () => void submitHitlDecision('respond'), disabled: submittingHitl, className: "rounded-lg border border-cyan-200 bg-white px-3 py-1.5 text-xs font-medium text-cyan-700 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-60", children: "\u63D0\u4EA4\u56DE\u5E94" })), hitlActions.includes('approve') && ((0, jsx_runtime_1.jsx)("button", { onClick: () => void submitHitlDecision('approve'), disabled: submittingHitl, className: "rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60", children: "\u901A\u8FC7" })), hitlActions.includes('edit') && ((0, jsx_runtime_1.jsx)("button", { onClick: () => void submitHitlDecision('edit'), disabled: submittingHitl, className: "rounded-lg border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60", children: "\u63D0\u4EA4\u7F16\u8F91" })), hitlActions.includes('reject') && ((0, jsx_runtime_1.jsx)("button", { onClick: () => void submitHitlDecision('reject'), disabled: submittingHitl, className: "rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60", children: "\u62D2\u7EDD" }))] })] }) })), (0, jsx_runtime_1.jsx)("div", { className: "flex-1 overflow-y-auto px-4 py-5 lg:px-6", children: displayMessages.length === 0 ? ((0, jsx_runtime_1.jsx)(ChatEmptyState_1.default, { prompts: SUGGESTED_PROMPTS, onSelectPrompt: setInput })) : ((0, jsx_runtime_1.jsx)(ChatMessageList_1.default, { messages: displayMessages, isRunning: isRunning || isReplaying, isReplaying: isReplaying, messagesEndRef: messagesEndRef, onRegenerate: handleRegenerate })) }), (0, jsx_runtime_1.jsx)(ChatComposer_1.default, { input: input, isRunning: isRunning || isReplaying, hasMessages: messages.length > 0 || Boolean(streamingSession.pendingUserMessage), retryTitle: "\u7EE7\u7EED / \u91CD\u8BD5 / \u91CD\u65B0\u751F\u6210", statusText: composerStatusText, textareaRef: textareaRef, onInputChange: setInput, onSend: handleSendMessage, onRetry: handleRetry, onInterrupt: handleInterrupt })] }) }));
}

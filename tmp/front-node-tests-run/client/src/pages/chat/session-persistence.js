"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadChatRunSnapshot = loadChatRunSnapshot;
exports.saveChatRunSnapshot = saveChatRunSnapshot;
exports.clearChatRunSnapshot = clearChatRunSnapshot;
const SNAPSHOT_KEY_PREFIX = 'client-chat-run-snapshot';
function getSnapshotKey(conversationId) {
    return `${SNAPSHOT_KEY_PREFIX}:${conversationId}`;
}
function loadChatRunSnapshot(conversationId) {
    if (typeof window === 'undefined')
        return null;
    try {
        const raw = window.sessionStorage.getItem(getSnapshotKey(conversationId));
        if (!raw)
            return null;
        const parsed = JSON.parse(raw);
        if (!parsed?.conversationId || parsed.conversationId !== conversationId)
            return null;
        return parsed;
    }
    catch {
        return null;
    }
}
function saveChatRunSnapshot(snapshot) {
    if (typeof window === 'undefined')
        return;
    try {
        window.sessionStorage.setItem(getSnapshotKey(snapshot.conversationId), JSON.stringify(snapshot));
    }
    catch {
        // Ignore sessionStorage write failures so chat streaming keeps working.
    }
}
function clearChatRunSnapshot(conversationId) {
    if (typeof window === 'undefined')
        return;
    try {
        window.sessionStorage.removeItem(getSnapshotKey(conversationId));
    }
    catch {
        // Ignore sessionStorage cleanup failures.
    }
}

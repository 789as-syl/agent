import type { StreamingSessionState } from './streaming-session'

export interface ChatRunSnapshot {
  conversationId: string
  runId: string | null
  lastEventId?: string | null
  session: StreamingSessionState
}

const SNAPSHOT_KEY_PREFIX = 'client-chat-run-snapshot'

function getSnapshotKey(conversationId: string) {
  return `${SNAPSHOT_KEY_PREFIX}:${conversationId}`
}

export function loadChatRunSnapshot(conversationId: string): ChatRunSnapshot | null {
  if (typeof window === 'undefined') return null

  try {
    const raw = window.sessionStorage.getItem(getSnapshotKey(conversationId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as ChatRunSnapshot
    if (!parsed?.conversationId || parsed.conversationId !== conversationId) return null
    return parsed
  } catch {
    return null
  }
}

export function saveChatRunSnapshot(snapshot: ChatRunSnapshot): void {
  if (typeof window === 'undefined') return

  try {
    window.sessionStorage.setItem(getSnapshotKey(snapshot.conversationId), JSON.stringify(snapshot))
  } catch {
    // Ignore sessionStorage write failures so chat streaming keeps working.
  }
}

export function clearChatRunSnapshot(conversationId: string): void {
  if (typeof window === 'undefined') return

  try {
    window.sessionStorage.removeItem(getSnapshotKey(conversationId))
  } catch {
    // Ignore sessionStorage cleanup failures.
  }
}

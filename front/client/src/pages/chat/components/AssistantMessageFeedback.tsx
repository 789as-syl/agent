import { useEffect, useState } from 'react'
import { Flag, MessageSquareWarning, ThumbsDown, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'

import { getMessageFeedback, upsertMessageFeedback } from '../../../api'
import type { MessageFeedbackResponse, MessageFeedbackUpsertRequest } from '../../../types'

function buildClass(active: boolean, tone: 'good' | 'bad' | 'warn') {
  if (tone === 'good') {
    return active
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : 'border-slate-200 bg-white text-slate-500 hover:border-emerald-200 hover:text-emerald-700'
  }
  if (tone === 'bad') {
    return active
      ? 'border-rose-200 bg-rose-50 text-rose-700'
      : 'border-slate-200 bg-white text-slate-500 hover:border-rose-200 hover:text-rose-700'
  }
  return active
    ? 'border-amber-200 bg-amber-50 text-amber-700'
    : 'border-slate-200 bg-white text-slate-500 hover:border-amber-200 hover:text-amber-700'
}

export default function AssistantMessageFeedback({ messageId }: { messageId: string }) {
  const [loading, setLoading] = useState(false)
  const [feedback, setFeedback] = useState<MessageFeedbackResponse | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const response = await getMessageFeedback(messageId)
        if (active) {
          setFeedback(response || null)
        }
      } catch {
        if (active) {
          setFeedback(null)
        }
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [messageId])

  const submit = async (payload: MessageFeedbackUpsertRequest) => {
    setLoading(true)
    try {
      const response = await upsertMessageFeedback(messageId, payload)
      setFeedback(response)
      toast.success('反馈已记录')
    } catch {
      toast.error('提交反馈失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        disabled={loading}
        onClick={() => void submit({ rating: 'helpful', evidence_quality: 'sufficient', hallucination_flag: false })}
        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${buildClass(feedback?.rating === 'helpful', 'good')}`}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
        有帮助
      </button>
      <button
        disabled={loading}
        onClick={() => void submit({ rating: 'not_helpful', evidence_quality: feedback?.evidence_quality ?? 'insufficient', hallucination_flag: false })}
        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${buildClass(feedback?.rating === 'not_helpful' && !feedback?.hallucination_flag, 'bad')}`}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
        帮助不足
      </button>
      <button
        disabled={loading}
        onClick={() => void submit({ rating: 'not_helpful', evidence_quality: 'missing', hallucination_flag: false })}
        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${buildClass(feedback?.evidence_quality === 'missing', 'warn')}`}
      >
        <MessageSquareWarning className="h-3.5 w-3.5" />
        证据不足
      </button>
      <button
        disabled={loading}
        onClick={() => void submit({ rating: 'not_helpful', evidence_quality: feedback?.evidence_quality ?? 'insufficient', hallucination_flag: true })}
        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${buildClass(Boolean(feedback?.hallucination_flag), 'bad')}`}
      >
        <Flag className="h-3.5 w-3.5" />
        疑似幻觉
      </button>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { RefreshCcw, Search } from 'lucide-react'
import { toast } from 'sonner'

import { getTraceRun, listTraceRuns } from '../api'
import type { AdminTraceRunDetailResponse, AdminTraceRunSummary } from '../types'

export default function TraceLabPage() {
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [runs, setRuns] = useState<AdminTraceRunSummary[]>([])
  const [selectedRun, setSelectedRun] = useState<AdminTraceRunDetailResponse | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  const loadRuns = async () => {
    setLoading(true)
    try {
      const response = await listTraceRuns({ page: 1, page_size: 20, q: query || undefined })
      setRuns(response.items)
      if (!selectedRunId && response.items[0]) {
        setSelectedRunId(response.items[0].id)
      }
    } catch {
      toast.error('加载 Trace Lab 列表失败')
    } finally {
      setLoading(false)
    }
  }

  const loadRunDetail = async (runId: string) => {
    try {
      const response = await getTraceRun(runId, { limit: 200 })
      setSelectedRun(response)
    } catch {
      toast.error('加载运行详情失败')
    }
  }

  useEffect(() => {
    void loadRuns()
  }, [])

  useEffect(() => {
    if (!selectedRunId) return
    void loadRunDetail(selectedRunId)
  }, [selectedRunId])

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Trace Lab</h1>
            <p className="mt-1 text-sm text-slate-500">查看已脱敏的运行时间线与工具执行轨迹。</p>
          </div>
          <button
            onClick={() => void loadRuns()}
            className="rounded-xl border border-slate-200 bg-slate-50 p-2 text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
          >
            <RefreshCcw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="relative mb-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void loadRuns()
            }}
            placeholder="按问题关键字检索运行"
            className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none focus:border-indigo-300 focus:bg-white"
          />
        </div>

        <div className="space-y-2">
          {runs.map((run) => (
            <button
              key={run.id}
              onClick={() => setSelectedRunId(run.id)}
              className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                selectedRunId === run.id ? 'border-indigo-200 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="line-clamp-2 text-sm font-medium text-slate-800">{run.query}</p>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600">{run.status}</span>
              </div>
              <p className="mt-2 text-xs text-slate-500">{new Date(run.created_at).toLocaleString()}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {!selectedRun ? (
          <div className="flex h-full min-h-[420px] items-center justify-center text-sm text-slate-500">请选择一条运行记录。</div>
        ) : (
          <div className="space-y-5">
            <div className="border-b border-slate-200 pb-4">
              <h2 className="text-xl font-semibold text-slate-900">{selectedRun.run.query}</h2>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                <span>状态：{selectedRun.run.status}</span>
                <span>事件数：{selectedRun.events.length}</span>
                <span>脱敏策略：{selectedRun.redaction_policy}</span>
              </div>
            </div>

            <div className="space-y-3">
              {selectedRun.events.map((event) => (
                <div key={event.event_id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{event.title}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        step={event.step} · kind={event.kind} · status={event.status}
                      </p>
                    </div>
                    <span className="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{event.event_type}</span>
                  </div>
                  {event.detail_sanitized && (
                    <pre className="mt-3 overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-6 text-slate-200">
                      {event.detail_sanitized}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

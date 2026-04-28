import { useEffect, useMemo, useState } from 'react'
import { Beaker, Play, Plus, RefreshCcw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { createEvalRun, createGoldenQuery, deleteGoldenQuery, listEvalRuns, listGoldenQueries } from '../api'
import type { RagEvalRunResponse, RagGoldenQueryResponse } from '../types'

export default function RagEvalLabPage() {
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [running, setRunning] = useState(false)
  const [goldenQueries, setGoldenQueries] = useState<RagGoldenQueryResponse[]>([])
  const [runs, setRuns] = useState<RagEvalRunResponse[]>([])
  const [selectedGoldenQueryId, setSelectedGoldenQueryId] = useState<string>('')
  const [name, setName] = useState('')
  const [query, setQuery] = useState('')
  const [expectedSources, setExpectedSources] = useState('')
  const [tags, setTags] = useState('')
  const [adhocQuery, setAdhocQuery] = useState('')

  const loadData = async () => {
    setLoading(true)
    try {
      const [goldenResponse, runsResponse] = await Promise.all([
        listGoldenQueries({ page: 1, page_size: 20 }),
        listEvalRuns({ page: 1, page_size: 20 }),
      ])
      setGoldenQueries(goldenResponse.items)
      setRuns(runsResponse.items)
      if (!selectedGoldenQueryId && goldenResponse.items[0]) {
        setSelectedGoldenQueryId(goldenResponse.items[0].id)
      }
    } catch {
      toast.error('加载 Eval Lab 数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  const selectedGoldenQuery = useMemo(
    () => goldenQueries.find((item) => item.id === selectedGoldenQueryId) ?? null,
    [goldenQueries, selectedGoldenQueryId]
  )

  const handleCreateGoldenQuery = async () => {
    if (!name.trim() || !query.trim()) {
      toast.error('请填写名称和查询语句')
      return
    }
    setCreating(true)
    try {
      await createGoldenQuery({
        name: name.trim(),
        query: query.trim(),
        expected_source_ids: expectedSources
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        tags: tags.split(',').map((item) => item.trim()).filter(Boolean),
        expected_answer: null,
      })
      setName('')
      setQuery('')
      setExpectedSources('')
      setTags('')
      toast.success('Golden Query 已创建')
      await loadData()
    } catch {
      toast.error('创建 Golden Query 失败')
    } finally {
      setCreating(false)
    }
  }

  const handleRunSelected = async () => {
    if (!selectedGoldenQueryId) {
      toast.error('请选择要运行的 Golden Query')
      return
    }
    setRunning(true)
    try {
      await createEvalRun({ golden_query_id: selectedGoldenQueryId })
      toast.success('评测任务已提交')
      await loadData()
    } catch {
      toast.error('运行评测失败')
    } finally {
      setRunning(false)
    }
  }

  const handleRunAdhoc = async () => {
    if (!adhocQuery.trim()) {
      toast.error('请输入临时评测问题')
      return
    }
    setRunning(true)
    try {
      await createEvalRun({ query: adhocQuery.trim() })
      setAdhocQuery('')
      toast.success('临时评测已提交')
      await loadData()
    } catch {
      toast.error('运行临时评测失败')
    } finally {
      setRunning(false)
    }
  }

  const handleDeleteGoldenQuery = async (queryId: string) => {
    if (!confirm('确认删除该 Golden Query 吗？')) return
    try {
      await deleteGoldenQuery(queryId)
      toast.success('已删除 Golden Query')
      await loadData()
    } catch {
      toast.error('删除 Golden Query 失败')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">RAG Eval Lab</h1>
          <p className="mt-1 text-sm text-slate-500">管理黄金查询并运行当前证据引擎评测。</p>
        </div>
        <button
          onClick={() => void loadData()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
        >
          <RefreshCcw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Plus className="h-5 w-5 text-indigo-500" />
            <h2 className="text-lg font-semibold text-slate-900">新建 Golden Query</h2>
          </div>
          <div className="space-y-3">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="名称"
              className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
            />
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="查询语句"
              rows={4}
              className="w-full rounded-xl border border-slate-200 p-3 text-sm"
            />
            <input
              value={expectedSources}
              onChange={(event) => setExpectedSources(event.target.value)}
              placeholder="期望证据 ID，逗号分隔"
              className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
            />
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="标签，逗号分隔"
              className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
            />
            <button
              onClick={() => void handleCreateGoldenQuery()}
              disabled={creating}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              <Plus className="h-4 w-4" />
              {creating ? '创建中...' : '创建'}
            </button>
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2">
              <Beaker className="h-5 w-5 text-emerald-500" />
              <h2 className="text-lg font-semibold text-slate-900">运行评测</h2>
            </div>
            <div className="flex flex-col gap-3 lg:flex-row">
              <select
                value={selectedGoldenQueryId}
                onChange={(event) => setSelectedGoldenQueryId(event.target.value)}
                className="h-10 flex-1 rounded-xl border border-slate-200 px-3 text-sm"
              >
                <option value="">选择 Golden Query</option>
                {goldenQueries.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <button
                onClick={() => void handleRunSelected()}
                disabled={running || !selectedGoldenQueryId}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                <Play className="h-4 w-4" />
                运行所选
              </button>
            </div>
            {selectedGoldenQuery && (
              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm font-semibold text-slate-800">{selectedGoldenQuery.name}</p>
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{selectedGoldenQuery.query}</p>
              </div>
            )}
            <div className="mt-4 border-t border-slate-200 pt-4">
              <textarea
                value={adhocQuery}
                onChange={(event) => setAdhocQuery(event.target.value)}
                placeholder="临时查询，不绑定 Golden Query"
                rows={3}
                className="w-full rounded-xl border border-slate-200 p-3 text-sm"
              />
              <button
                onClick={() => void handleRunAdhoc()}
                disabled={running}
                className="mt-3 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 hover:border-indigo-200 hover:text-indigo-600 disabled:opacity-60"
              >
                <Play className="h-4 w-4" />
                运行临时评测
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">Golden Query 列表</h2>
            <div className="space-y-3">
              {goldenQueries.map((item) => (
                <div key={item.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{item.name}</p>
                      <p className="mt-2 text-sm text-slate-600">{item.query}</p>
                    </div>
                    <button
                      onClick={() => void handleDeleteGoldenQuery(item.id)}
                      className="rounded-lg p-2 text-rose-600 hover:bg-rose-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">最近评测运行</h2>
            <div className="space-y-3">
              {runs.map((run) => (
                <div key={run.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{run.query}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        score={run.score.toFixed(2)} · evidence={run.evidence_count} · missing={run.missing_expected_count}
                      </p>
                    </div>
                    <span className="rounded-full bg-white px-2 py-1 text-[11px] text-slate-600">{run.status}</span>
                  </div>
                  {run.error_message && <p className="mt-2 text-sm text-rose-600">{run.error_message}</p>}
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

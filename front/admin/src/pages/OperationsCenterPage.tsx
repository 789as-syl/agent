import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, RefreshCcw, RotateCcw, Sparkles, Workflow } from 'lucide-react'
import { toast } from 'sonner'

import {
  getAdminFeedbackSummary,
  getQualityRadar,
  getTasks,
  listAdminFeedback,
  retryIngestionJob,
  retryVectorizationJob,
} from '../api'
import type {
  AdminMessageFeedbackItem,
  AdminMessageFeedbackSummaryResponse,
  AdminTaskConsoleItem,
  ContentQualityWarning,
  QualityRadarResponse,
} from '../types'

export default function OperationsCenterPage() {
  const [loading, setLoading] = useState(false)
  const [tasks, setTasks] = useState<AdminTaskConsoleItem[]>([])
  const [warnings, setWarnings] = useState<ContentQualityWarning[]>([])
  const [quality, setQuality] = useState<QualityRadarResponse | null>(null)
  const [feedbackSummary, setFeedbackSummary] = useState<AdminMessageFeedbackSummaryResponse | null>(null)
  const [feedbackItems, setFeedbackItems] = useState<AdminMessageFeedbackItem[]>([])
  const [retryingId, setRetryingId] = useState<string | null>(null)

  const loadData = async () => {
    setLoading(true)
    try {
      const [taskResponse, qualityResponse, feedbackSummaryResponse, feedbackListResponse] = await Promise.all([
        getTasks({ page: 1, page_size: 12 }),
        getQualityRadar(),
        getAdminFeedbackSummary(),
        listAdminFeedback({ page: 1, page_size: 8 }),
      ])
      setTasks(taskResponse.items)
      setQuality(qualityResponse)
      setWarnings(qualityResponse.warnings)
      setFeedbackSummary(feedbackSummaryResponse)
      setFeedbackItems(feedbackListResponse.items)
    } catch {
      toast.error('加载运维中心数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  const handleRetry = async (task: AdminTaskConsoleItem) => {
    if (task.status !== 'failed') return
    setRetryingId(task.id)
    try {
      if (task.task_type === 'ingestion') {
        await retryIngestionJob(task.id)
      } else {
        await retryVectorizationJob(task.id)
      }
      toast.success('已重新提交任务')
      await loadData()
    } catch {
      toast.error('任务重试失败')
    } finally {
      setRetryingId(null)
    }
  }

  const qualityCards = quality
    ? [
        { label: '文档数', value: quality.document_count },
        { label: '分块数', value: quality.chunk_count },
        { label: '题目数', value: quality.question_count },
        { label: '待修复告警', value: warnings.length },
      ]
    : []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">运维与质量中心</h1>
          <p className="mt-1 text-sm text-slate-500">统一查看任务、内容质量和用户反馈信号。</p>
        </div>
        <button
          onClick={() => void loadData()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
        >
          <RefreshCcw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {qualityCards.map((card) => (
          <div key={card.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">{card.label}</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">{loading ? '...' : card.value}</p>
          </div>
        ))}
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-amber-500" />
          <h2 className="text-lg font-semibold text-slate-900">内容质量雷达</h2>
        </div>
        {warnings.length === 0 ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            当前没有待处理的质量告警。
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {warnings.map((warning) => (
              <div
                key={`${warning.code}-${warning.resource_id ?? warning.resource_type}`}
                className={`rounded-xl border px-4 py-3 ${
                  warning.severity === 'critical'
                    ? 'border-rose-200 bg-rose-50'
                    : warning.severity === 'warning'
                      ? 'border-amber-200 bg-amber-50'
                      : 'border-sky-200 bg-sky-50'
                }`}
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="text-sm font-semibold text-slate-900">{warning.title}</span>
                </div>
                <p className="mt-2 text-sm text-slate-600">{warning.detail}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <Workflow className="h-5 w-5 text-indigo-500" />
          <h2 className="text-lg font-semibold text-slate-900">任务控制台</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2">类型</th>
                <th className="px-3 py-2">任务</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">进度</th>
                <th className="px-3 py-2">时间</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td className="px-3 py-3 text-slate-600">{task.task_type === 'ingestion' ? '入库' : '向量化'}</td>
                  <td className="px-3 py-3">
                    <p className="font-medium text-slate-800">{task.title}</p>
                    {task.error_message && <p className="mt-1 text-xs text-rose-600">{task.error_message}</p>}
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        task.status === 'success'
                          ? 'bg-emerald-50 text-emerald-700'
                          : task.status === 'failed'
                            ? 'bg-rose-50 text-rose-700'
                            : 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      {task.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-slate-600">{task.progress}%</td>
                  <td className="px-3 py-3 text-slate-500">{new Date(task.created_at).toLocaleString()}</td>
                  <td className="px-3 py-3 text-right">
                    <button
                      disabled={task.status !== 'failed' || retryingId === task.id}
                      onClick={() => void handleRetry(task)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      重试
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          <h2 className="text-lg font-semibold text-slate-900">回答反馈</h2>
        </div>
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {[
            ['总反馈', feedbackSummary?.total_feedback ?? 0],
            ['认可', feedbackSummary?.helpful_count ?? 0],
            ['不认可', feedbackSummary?.not_helpful_count ?? 0],
            ['幻觉标记', feedbackSummary?.hallucination_count ?? 0],
            ['证据缺失', feedbackSummary?.evidence_missing_count ?? 0],
            ['有评论', feedbackSummary?.comment_count ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
              <p className="text-xs text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
            </div>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2">用户</th>
                <th className="px-3 py-2">评分</th>
                <th className="px-3 py-2">证据</th>
                <th className="px-3 py-2">消息摘要</th>
                <th className="px-3 py-2">评论</th>
                <th className="px-3 py-2">时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {feedbackItems.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-3 text-slate-700">{item.user_phone}</td>
                  <td className="px-3 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-medium ${item.rating === 'helpful' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                      {item.rating === 'helpful' ? '认可' : '不认可'}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-slate-600">
                    {item.evidence_quality || '未标记'}
                    {item.hallucination_flag ? ' · 幻觉' : ''}
                  </td>
                  <td className="px-3 py-3 text-slate-700">{item.message_preview}</td>
                  <td className="px-3 py-3 text-slate-500">{item.comment || '-'}</td>
                  <td className="px-3 py-3 text-slate-500">{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { RefreshCcw, Search } from 'lucide-react'
import { toast } from 'sonner'

import { listAuditLogs } from '../api'
import type { AdminAuditLogResponse } from '../types'

export default function AuditLogPage() {
  const [loading, setLoading] = useState(false)
  const [action, setAction] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [items, setItems] = useState<AdminAuditLogResponse[]>([])

  const loadData = async () => {
    setLoading(true)
    try {
      const response = await listAuditLogs({
        page: 1,
        page_size: 30,
        action: action || undefined,
        resource_type: resourceType || undefined,
      })
      setItems(response.items)
    } catch {
      toast.error('加载审计日志失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">审计日志</h1>
          <p className="mt-1 text-sm text-slate-500">查看管理员内容操作、评测运行与任务重试痕迹。</p>
        </div>
        <button
          onClick={() => void loadData()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
        >
          <RefreshCcw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_auto]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={action}
              onChange={(event) => setAction(event.target.value)}
              placeholder="按 action 过滤"
              className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none focus:border-indigo-300 focus:bg-white"
            />
          </div>
          <input
            value={resourceType}
            onChange={(event) => setResourceType(event.target.value)}
            placeholder="按 resource_type 过滤"
            className="h-10 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-300 focus:bg-white"
          />
          <button
            onClick={() => void loadData()}
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white"
          >
            查询
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2">时间</th>
                <th className="px-3 py-2">动作</th>
                <th className="px-3 py-2">资源</th>
                <th className="px-3 py-2">摘要</th>
                <th className="px-3 py-2">元数据</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="px-3 py-3 text-slate-500">{new Date(item.created_at).toLocaleString()}</td>
                  <td className="px-3 py-3 font-medium text-slate-800">{item.action}</td>
                  <td className="px-3 py-3 text-slate-600">
                    {item.resource_type}
                    {item.resource_id ? ` · ${item.resource_id}` : ''}
                  </td>
                  <td className="px-3 py-3 text-slate-700">{item.summary}</td>
                  <td className="px-3 py-3 text-slate-500">
                    <pre className="max-w-[340px] overflow-auto whitespace-pre-wrap text-xs">
                      {JSON.stringify(item.metadata_json, null, 2)}
                    </pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

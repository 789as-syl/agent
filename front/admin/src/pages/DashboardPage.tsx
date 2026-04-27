import { useEffect, useMemo, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { BarChart, LineChart, PieChart as EChartsPieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { motion } from 'framer-motion'
import {
  Activity,
  BarChart3,
  Calendar,
  Clock3,
  Database,
  PieChart,
  Target,
} from 'lucide-react'
import { getAdminDashboard } from '../api'
import type { AdminDashboardResponse, AdminRange } from '../types'

const rangeItems: Array<{ label: string; value: AdminRange }> = [
  { label: '今日', value: '1d' },
  { label: '近7天', value: '7d' },
  { label: '近30天', value: '30d' },
]

echarts.use([LineChart, BarChart, EChartsPieChart, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

export default function DashboardPage() {
  const [range, setRange] = useState<AdminRange>('7d')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<AdminDashboardResponse | null>(null)

  useEffect(() => {
    let active = true
    const run = async () => {
      setLoading(true)
      try {
        const response = await getAdminDashboard(range)
        if (active) setData(response)
      } catch {
        if (active) setData(null)
      } finally {
        if (active) setLoading(false)
      }
    }
    void run()
    return () => {
      active = false
    }
  }, [range])

  const trendOption = useMemo<EChartsOption>(() => {
    const points = data?.trends ?? []
    return {
      tooltip: { trigger: 'axis' },
      grid: { top: 36, left: 20, right: 12, bottom: 24, containLabel: true },
      legend: { data: ['请求量', '命中量'], top: 0 },
      xAxis: { type: 'category', data: points.map((item) => item.bucket) },
      yAxis: { type: 'value' },
      series: [
        {
          name: '请求量',
          type: 'line',
          smooth: true,
          data: points.map((item) => item.request_count),
          lineStyle: { width: 2.5, color: '#6366f1' },
          itemStyle: { color: '#6366f1' },
        },
        {
          name: '命中量',
          type: 'line',
          smooth: true,
          data: points.map((item) => item.hit_count),
          lineStyle: { width: 2.5, color: '#10b981' },
          itemStyle: { color: '#10b981' },
        },
      ],
    }
  }, [data])

  const breakdownOption = useMemo<EChartsOption>(() => {
    const source = data?.result_breakdown ?? []
    return {
      tooltip: { trigger: 'item' },
      legend: { orient: 'vertical', right: 8, top: 'center' },
      series: [
        {
          name: '检索结果构成',
          type: 'pie',
          radius: ['46%', '72%'],
          center: ['36%', '50%'],
          itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          data: source.map((item) => ({ value: item.value, name: item.label })),
        },
      ],
    }
  }, [data])

  const heatOption = useMemo<EChartsOption>(() => {
    const source = data?.knowledge_heat ?? []
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { top: 24, left: 12, right: 12, bottom: 24, containLabel: true },
      xAxis: { type: 'category', data: source.map((item) => item.title) },
      yAxis: { type: 'value' },
      series: [
        {
          name: '热度',
          type: 'bar',
          barWidth: 26,
          data: source.map((item) => item.count),
          itemStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: '#8b5cf6' },
                { offset: 1, color: '#6366f1' },
              ],
            },
            borderRadius: [8, 8, 0, 0],
          },
        },
      ],
    }
  }, [data])

  const metrics = data?.metrics ?? {
    request_count: 0,
    hit_rate: 0,
    avg_latency_ms: 0,
    document_count: 0,
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">数据看板</h1>
          <p className="mt-1 text-sm text-slate-500">查看检索质量、响应效率与知识库覆盖情况。</p>
        </div>

        <div className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1">
          <Calendar className="ml-1 h-4 w-4 text-slate-400" />
          {rangeItems.map((item) => (
            <button
              key={item.value}
              onClick={() => setRange(item.value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                range === item.value
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          { title: '请求量', value: metrics.request_count, icon: BarChart3, color: 'text-indigo-600' },
          { title: '命中率', value: `${metrics.hit_rate.toFixed(2)}%`, icon: Target, color: 'text-emerald-600' },
          {
            title: '平均时延',
            value: `${Math.round(metrics.avg_latency_ms)}ms`,
            icon: Clock3,
            color: 'text-amber-600',
          },
          { title: '文档数', value: metrics.document_count, icon: Database, color: 'text-violet-600' },
        ].map((item, index) => {
          const Icon = item.icon
          return (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.07, duration: 0.28 }}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-slate-500">{item.title}</p>
                  <p className="mt-1 text-3xl font-semibold text-slate-900">
                    {loading ? '...' : item.value}
                  </p>
                </div>
                <div className={`flex h-11 w-11 items-center justify-center rounded-xl border bg-slate-50 ${item.color}`}>
                  <Icon className="h-5 w-5" />
                </div>
              </div>
            </motion.div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-3"
        >
          <div className="mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5 text-indigo-600" />
            <h2 className="text-sm font-semibold text-slate-900">请求趋势</h2>
          </div>
          <div className="h-80">
            <ReactEChartsCore echarts={echarts} option={trendOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.26 }}
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2"
        >
          <div className="mb-4 flex items-center gap-2">
            <PieChart className="h-5 w-5 text-emerald-600" />
            <h2 className="text-sm font-semibold text-slate-900">结果构成</h2>
          </div>
          <div className="h-80">
            <ReactEChartsCore echarts={echarts} option={breakdownOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </motion.section>
      </div>

      <motion.section
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.34 }}
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <div className="mb-4 flex items-center gap-2">
          <Database className="h-5 w-5 text-violet-600" />
          <h2 className="text-sm font-semibold text-slate-900">知识点热度</h2>
        </div>
        <div className="h-80">
          <ReactEChartsCore echarts={echarts} option={heatOption} style={{ height: '100%', width: '100%' }} />
        </div>
      </motion.section>
    </div>
  )
}

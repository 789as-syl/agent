import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import axios from 'axios'
import { toast } from 'sonner'
import {
  ExternalLink,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-react'

import { extractApiErrorMessage } from '../api'
import { getKnowledgeGraph } from '../api/admin-analytics'
import * as adminIngestionApi from '../api/admin-ingestion'
import * as adminQuestionsApi from '../api/admin-questions'
import DocumentPreviewFrame from '../components/documents/DocumentPreviewFrame'
import NodeDetailModal from '../components/NodeDetailModal'
import {
  buildQuestionWritePayload,
  createEmptyQuestionEditorState,
  questionToEditorState,
  type QuestionEditorFormState,
} from '../components/questions/questionEditorUtils'
import type {
  AdminRange,
  GraphNode,
  KnowledgeGraphResponse,
  KnowledgePointResponse,
  QuestionType,
  QuestionResponse,
} from '../types'

type NodeCategory = 'all' | 'knowledge_point' | 'question'

echarts.use([GraphChart, TooltipComponent, CanvasRenderer])

const rangeItems: Array<{ label: string; value: AdminRange }> = [
  { label: '今日', value: '1d' },
  { label: '近7天', value: '7d' },
  { label: '近30天', value: '30d' },
]

const questionTypeOptions: Array<{ label: string; value: QuestionType }> = [
  { label: '单选题', value: 'single' },
  { label: '多选题', value: 'multiple' },
  { label: '判断题', value: 'true_false' },
  { label: '简答题', value: 'short_answer' },
]

interface EchartsNode {
  id: string
  name: string
  symbolSize: number
  category: number
  value: number
  itemStyle: {
    color: string
    borderColor?: string
    borderWidth?: number
    shadowBlur?: number
    shadowColor?: string
  }
  raw: GraphNode
}

interface EchartsLink {
  source: string
  target: string
  value: number
}

const truncateLabel = (value: string, limit = 18): string => {
  if (value.length <= limit) return value
  return `${value.slice(0, limit - 1)}…`
}

export default function KnowledgeGraphPage() {
  const chartRef = useRef<ReactEChartsCore>(null)
  const graphRequestSeqRef = useRef(0)
  const detailRequestSeqRef = useRef(0)
  const graphAbortRef = useRef<AbortController | null>(null)
  const hasGraphDataRef = useRef(false)

  const [zoom, setZoom] = useState(1)
  const [categoryFilter, setCategoryFilter] = useState<NodeCategory>('all')
  const [range, setRange] = useState<AdminRange>('7d')
  const [data, setData] = useState<KnowledgeGraphResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [knowledgePointDetail, setKnowledgePointDetail] = useState<KnowledgePointResponse | null>(null)
  const [questionDetail, setQuestionDetail] = useState<QuestionResponse | null>(null)
  const [questionForm, setQuestionForm] = useState<QuestionEditorFormState>(() => createEmptyQuestionEditorState())
  const [questionSaving, setQuestionSaving] = useState(false)
  const [questionEditMode, setQuestionEditMode] = useState(false)
  const [knowledgePointCandidates, setKnowledgePointCandidates] = useState<KnowledgePointResponse[]>([])
  const [selectedKnowledgeIds, setSelectedKnowledgeIds] = useState<Set<string>>(new Set())
  const [showAllChunks, setShowAllChunks] = useState(false)
  const [deletingKnowledgePoint, setDeletingKnowledgePoint] = useState(false)

  const [chunkSearch, setChunkSearch] = useState('')
  const [knowledgeSearch, setKnowledgeSearch] = useState('')
  const [documentPreviewOpen, setDocumentPreviewOpen] = useState(false)
  const [documentPreviewUrl, setDocumentPreviewUrl] = useState('')
  const [documentPreviewState, setDocumentPreviewState] = useState<adminIngestionApi.KnowledgePointPreviewState | null>(
    null
  )
  const [documentPreviewStateMessage, setDocumentPreviewStateMessage] = useState('')
  const [documentLoading, setDocumentLoading] = useState(false)

  const loadGraph = useCallback(async (selectedRange: AdminRange, forceRefresh = false) => {
    const seq = graphRequestSeqRef.current + 1
    graphRequestSeqRef.current = seq
    graphAbortRef.current?.abort()
    const controller = new AbortController()
    graphAbortRef.current = controller

    if (hasGraphDataRef.current) setRefreshing(true)
    else setLoading(true)
    setLoadError(null)

    try {
      const response = await getKnowledgeGraph(selectedRange, 200, {
        includeOrphanQuestions: true,
        forceRefresh,
        requestConfig: { signal: controller.signal },
      })
      if (graphRequestSeqRef.current !== seq) return
      setData(response)
      hasGraphDataRef.current = true
    } catch (error) {
      if (controller.signal.aborted) return
      if (axios.isAxiosError(error) && error.code === 'ERR_CANCELED') return
      if (graphRequestSeqRef.current !== seq) return
      setData(null)
      hasGraphDataRef.current = false
      setLoadError(extractApiErrorMessage(error, '知识图谱加载失败'))
    } finally {
      if (graphRequestSeqRef.current === seq) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  const loadNodeDetail = async (node: GraphNode) => {
    const seq = detailRequestSeqRef.current + 1
    detailRequestSeqRef.current = seq

    setDetailLoading(true)
    setDetailError(null)
    setChunkSearch('')
    setKnowledgeSearch('')
    setKnowledgePointDetail(null)
    setQuestionDetail(null)
    setKnowledgePointCandidates([])
    setSelectedKnowledgeIds(new Set())
    setQuestionEditMode(false)
    setShowAllChunks(false)

    try {
      if (node.node_type === 'knowledge_point') {
        const detail = await adminIngestionApi.getKnowledgePoint(node.id)
        if (detailRequestSeqRef.current !== seq) return
        setKnowledgePointDetail(detail)
        return
      }

      const [question, knowledgePointList] = await Promise.all([
        adminQuestionsApi.getQuestion(node.id),
        adminIngestionApi.getKnowledgePoints({ page: 1, page_size: 200, include_chunks: false }),
      ])
      if (detailRequestSeqRef.current !== seq) return

      setQuestionDetail(question)
      setQuestionForm(questionToEditorState(question))
      setKnowledgePointCandidates(knowledgePointList.items)
      setSelectedKnowledgeIds(new Set(question.knowledge_point_ids ?? []))
    } catch (error) {
      if (detailRequestSeqRef.current !== seq) return
      setDetailError(extractApiErrorMessage(error, '节点详情加载失败'))
    } finally {
      if (detailRequestSeqRef.current === seq) {
        setDetailLoading(false)
      }
    }
  }

  
  const closeNodeCard = () => {
    setSelectedNode(null)
    setQuestionEditMode(false)
    setShowAllChunks(false)
    setDetailError(null)
    setKnowledgePointDetail(null)
    setQuestionDetail(null)
    setQuestionForm(createEmptyQuestionEditorState())
    setDeletingKnowledgePoint(false)
    setDocumentPreviewOpen(false)
    setDocumentPreviewUrl('')
    setDocumentPreviewState(null)
    setDocumentPreviewStateMessage('')
  }

  const openNodeCard = (node: GraphNode) => {
    setSelectedNode(node)
    setQuestionEditMode(false)
    setShowAllChunks(false)
    void loadNodeDetail(node)
  }
  const handleSaveQuestion = async () => {
    if (!questionDetail) return
    const result = buildQuestionWritePayload(questionForm)
    if (result.error || !result.payload) {
      toast.error(result.error ?? '题目参数不完整')
      return
    }

    setQuestionSaving(true)
    try {
      await adminQuestionsApi.updateQuestion(questionDetail.id, result.payload)
      await adminQuestionsApi.linkKnowledgePoints(questionDetail.id, {
        knowledge_point_ids: [...selectedKnowledgeIds],
      })

      const refreshedQuestion = await adminQuestionsApi.getQuestion(questionDetail.id)
      setQuestionDetail(refreshedQuestion)
      setQuestionForm(questionToEditorState(refreshedQuestion))
      setSelectedKnowledgeIds(new Set(refreshedQuestion.knowledge_point_ids ?? []))
      setSelectedNode((prev) =>
        prev
          ? {
              ...prev,
              label: refreshedQuestion.question_text,
              is_orphan: refreshedQuestion.knowledge_point_ids.length === 0,
            }
          : prev
      )

      toast.success('题目更新成功')
      await loadGraph(range, true)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '题目更新失败'))
    } finally {
      setQuestionSaving(false)
    }
  }

  const handleOpenDocumentPreview = async () => {
    if (!knowledgePointDetail) return
    setDocumentLoading(true)
    try {
      const preview = await adminIngestionApi.getKnowledgePointDocumentUrl(knowledgePointDetail.id)
      const resolvedPreview = adminIngestionApi.resolveKnowledgePointDocumentPreview(preview)
      setDocumentPreviewUrl(resolvedPreview.url)
      setDocumentPreviewState(resolvedPreview.state)
      setDocumentPreviewStateMessage(resolvedPreview.stateMessage)
      setDocumentPreviewOpen(true)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '文档预览地址获取失败'))
    } finally {
      setDocumentLoading(false)
    }
  }

  const handleDeleteKnowledgePoint = async () => {
    if (!knowledgePointDetail || deletingKnowledgePoint) return

    const confirmed = window.confirm(
      `确认删除文档「${knowledgePointDetail.title}」？这会同时删除解析切片、向量数据、对象存储文件以及相关入库任务绑定。`
    )
    if (!confirmed) return

    setDeletingKnowledgePoint(true)
    try {
      const result = await adminIngestionApi.deleteKnowledgePoint(knowledgePointDetail.id)
      setDocumentPreviewOpen(false)
      setDocumentPreviewUrl('')
      setDocumentPreviewState(null)
      setDocumentPreviewStateMessage('')
      closeNodeCard()
      await loadGraph(range, true)
      toast.success(`文档已删除，清理 ${result.deleted_chunk_count} 个切片`)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '删除文档失败'))
    } finally {
      setDeletingKnowledgePoint(false)
    }
  }

  useEffect(() => {
    void loadGraph(range)
    return () => graphAbortRef.current?.abort()
  }, [loadGraph, range])

  const graphData = useMemo(() => {
    const nodes = (data?.nodes ?? []).map<EchartsNode>((node) => {
      const isKnowledgePoint = node.node_type === 'knowledge_point'
      const isOrphan = node.node_type === 'question' && Boolean(node.is_orphan)
      const isFocused = selectedNode?.id === node.id
      const category = isKnowledgePoint ? 0 : isOrphan ? 2 : 1

      return {
        id: node.id,
        name: truncateLabel(node.label, node.node_type === 'question' ? 20 : 16),
        symbolSize: Math.max(22, Math.min(86, 20 + Math.round(node.weight))),
        category,
        value: node.weight,
        itemStyle: {
          color: isKnowledgePoint ? '#6366f1' : isOrphan ? '#f59e0b' : '#10b981',
          borderWidth: isFocused ? 3 : 1,
          borderColor: isFocused ? '#22d3ee' : 'rgba(255,255,255,0.5)',
          shadowBlur: isFocused ? 22 : 8,
          shadowColor: isFocused ? 'rgba(34,211,238,0.55)' : 'rgba(15,23,42,0.18)',
        },
        raw: node,
      }
    })

    const links = (data?.links ?? []).map<EchartsLink>((link) => ({
      source: link.source,
      target: link.target,
      value: link.weight,
    }))

    return { nodes, links }
  }, [data, selectedNode])

  const { nodes, links } = useMemo(() => {
    const allNodes = graphData.nodes
    const allLinks = graphData.links
    if (categoryFilter === 'all') return { nodes: allNodes, links: allLinks }

    const subset = categoryFilter === 'knowledge_point'
      ? allNodes.filter((node) => node.category === 0)
      : allNodes.filter((node) => node.category === 1 || node.category === 2)
    const idSet = new Set(subset.map((item) => item.id))
    return {
      nodes: subset,
      links: allLinks.filter((link) => idSet.has(link.source) && idSet.has(link.target)),
    }
  }, [categoryFilter, graphData])

  const selectedNodeConnections = useMemo(() => {
    if (!selectedNode) return 0
    return graphData.links.filter((link) => link.source === selectedNode.id || link.target === selectedNode.id).length
  }, [selectedNode, graphData.links])

  const filteredChunks = useMemo(() => {
    if (!knowledgePointDetail) return []
    const query = chunkSearch.trim().toLowerCase()
    const sorted = [...knowledgePointDetail.chunks].sort((a, b) => a.chunk_index - b.chunk_index)
    if (!query) return sorted
    return sorted.filter((chunk) => chunk.content.toLowerCase().includes(query))
  }, [knowledgePointDetail, chunkSearch])

  const visibleChunks = useMemo(() => {
    if (showAllChunks) return filteredChunks
    return filteredChunks.slice(0, 3)
  }, [filteredChunks, showAllChunks])

  const filteredKnowledgeCandidates = useMemo(() => {
    const query = knowledgeSearch.trim().toLowerCase()
    if (!query) return knowledgePointCandidates
    return knowledgePointCandidates.filter((item) => item.title.toLowerCase().includes(query))
  }, [knowledgePointCandidates, knowledgeSearch])

  const chartOption = useMemo<EChartsOption>(() => ({
    animationDuration: 500,
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const payload = params as { dataType?: string; data?: unknown }
        if (payload.dataType === 'edge') {
          const edge = payload.data as Partial<EchartsLink> | undefined
          return `${edge?.source ?? ''} → ${edge?.target ?? ''}`
        }

        const node = payload.data as Partial<EchartsNode> | undefined
        const raw = node?.raw
        const label = raw?.node_type === 'knowledge_point' ? '知识点' : raw?.is_orphan ? '题目（未关联）' : '题目'
        return `${raw?.label ?? node?.name ?? ''}<br/>分类：${label}<br/>连接数：${raw?.link_count ?? 0}`
      },
    },
    series: [{
      name: '知识图谱',
      type: 'graph',
      layout: 'force',
      roam: true,
      zoom,
      left: 8,
      right: 8,
      top: 8,
      bottom: 8,
      draggable: true,
      symbolSize: 48,
      label: { show: true, position: 'right', color: '#1e293b', fontSize: 12 },
      lineStyle: { color: 'rgba(99,102,241,0.3)', width: 1.4, curveness: 0.08 },
      edgeSymbol: ['circle', 'arrow'],
      edgeSymbolSize: [4, 8],
      force: { repulsion: 980, edgeLength: [120, 220], friction: 0.12 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 2 } },
      data: nodes,
      links,
      categories: [{ name: '知识点' }, { name: '题目' }, { name: '未关联题目' }],
    }],
  }), [nodes, links, zoom])

  const onEvents = {
    click: (params: {
      dataType?: string
      data?: EchartsNode
    }) => {
      if (params.dataType !== 'node' || !params.data?.raw) return

      const clickedNode = params.data.raw
      if (selectedNode?.id === clickedNode.id) {
        return
      }

      openNodeCard(clickedNode)
    },
  }

  const allNodes = data?.nodes ?? []
  const orphanQuestionCount = allNodes.filter((item) => item.node_type === 'question' && item.is_orphan).length
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">知识图谱</h1>
          <p className="mt-1 text-sm text-slate-500">展示知识点与题目关系，支持未关联题目独立展示与节点详情编辑。</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
            {rangeItems.map((item) => (
              <button
                key={item.value}
                onClick={() => setRange(item.value)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${range === item.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
            {[
              { key: 'all', label: '全部' },
              { key: 'knowledge_point', label: '知识点' },
              { key: 'question', label: '题目' },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => setCategoryFilter(item.key as NodeCategory)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${categoryFilter === item.key ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-slate-50/70 px-4 py-3">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <p className="text-xs leading-5 text-slate-500">
              可点击题目或知识点节点查看详情；题目节点支持按统一题型规则直接编辑。
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => setZoom((prev) => Math.max(0.6, Number((prev - 0.1).toFixed(2))))}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:border-slate-300 hover:text-slate-700"
                title="缩小"
              >
                <Minimize2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => setZoom((prev) => Math.min(2, Number((prev + 0.1).toFixed(2))))}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:border-slate-300 hover:text-slate-700"
                title="放大"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  setZoom(1)
                  void loadGraph(range, true)
                }}
                className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 text-xs font-medium text-slate-600 transition-all hover:border-slate-300 hover:text-slate-700"
              >
                <RotateCcw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                {refreshing ? '刷新中...' : '重置/刷新'}
              </button>
              {(loading || loadError) && (
                <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 shadow-sm">
                  {loading ? '知识图谱加载中...' : loadError}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="h-[72vh] min-h-[560px] w-full bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.08),transparent_58%)]">
          <ReactEChartsCore
            ref={chartRef}
            echarts={echarts}
            option={chartOption}
            style={{ height: '100%', width: '100%' }}
            onEvents={onEvents}
            notMerge
            lazyUpdate
          />
        </div>

        <div className="pointer-events-none absolute bottom-4 left-4 flex gap-3">
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700 shadow-sm">
            <p className="font-medium">知识点</p>
            <p className="mt-0.5 text-lg font-semibold text-indigo-600">{allNodes.filter((item) => item.node_type === 'knowledge_point').length}</p>
          </div>
          <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 shadow-sm">
            <p className="font-medium">已关联题目</p>
            <p className="mt-0.5 text-lg font-semibold text-emerald-600">{allNodes.filter((item) => item.node_type === 'question' && !item.is_orphan).length}</p>
          </div>
          <div className="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-700 shadow-sm">
            <p className="font-medium">未关联题目</p>
            <p className="mt-0.5 text-lg font-semibold text-amber-600">{orphanQuestionCount}</p>
          </div>
        </div>
      </div>

      <NodeDetailModal
        open={Boolean(selectedNode)}
        selectedNode={selectedNode}
        detailLoading={detailLoading}
        detailError={detailError}
        selectedNodeConnections={selectedNodeConnections}
        knowledgePointDetail={knowledgePointDetail}
        questionForm={questionForm}
        questionTypeOptions={questionTypeOptions}
        questionEditMode={questionEditMode}
        questionSaving={questionSaving}
        knowledgePointCandidates={filteredKnowledgeCandidates}
        selectedKnowledgeIds={selectedKnowledgeIds}
        chunkSearch={chunkSearch}
        filteredChunks={filteredChunks}
        visibleChunks={visibleChunks}
        showAllChunks={showAllChunks}
        documentLoading={documentLoading}
        knowledgeSearch={knowledgeSearch}
        deletingKnowledgePoint={deletingKnowledgePoint}
        onClose={closeNodeCard}
        onOpenDocumentPreview={() => void handleOpenDocumentPreview()}
        onDeleteKnowledgePoint={() => void handleDeleteKnowledgePoint()}
        onToggleQuestionEdit={() => setQuestionEditMode((prev) => !prev)}
        onChunkSearchChange={setChunkSearch}
        onKnowledgeSearchChange={setKnowledgeSearch}
        onToggleShowAllChunks={() => setShowAllChunks((prev) => !prev)}
        onQuestionFormChange={setQuestionForm}
        onToggleKnowledgeSelection={(id, checked) => {
          setSelectedKnowledgeIds((prev) => {
            const next = new Set(prev)
            if (checked) next.add(id)
            else next.delete(id)
            return next
          })
        }}
        onSaveQuestion={() => void handleSaveQuestion()}
      />

      {documentPreviewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 p-4 backdrop-blur-sm">
          <div className="w-full max-w-6xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-800">统一文档预览</div>
                {knowledgePointDetail?.title && (
                  <div className="truncate text-xs text-slate-500">{knowledgePointDetail.title}</div>
                )}
              </div>
              <button onClick={() => setDocumentPreviewOpen(false)} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-700"><X className="h-4 w-4" /></button>
            </div>
            <div className="h-[70vh] bg-slate-100">
              <div className="flex h-full flex-col p-3">
                <DocumentPreviewFrame
                  previewUrl={documentPreviewUrl}
                  previewState={documentPreviewState}
                  previewStateMessage={documentPreviewStateMessage}
                  className="min-h-0 flex-1 overflow-hidden rounded-lg border border-slate-200 bg-white"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-3 border-t border-slate-200 px-4 py-3">
              <a href={documentPreviewUrl} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:border-indigo-200 hover:text-indigo-600"><ExternalLink className="h-3.5 w-3.5" /> 新窗口打开</a>
              {knowledgePointDetail && (
                <button
                  onClick={() => void handleDeleteKnowledgePoint()}
                  disabled={deletingKnowledgePoint}
                  className="inline-flex h-9 items-center gap-2 rounded-lg border border-red-200 bg-white px-3 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {deletingKnowledgePoint ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                  删除文档
                </button>
              )}
              <button onClick={() => setDocumentPreviewOpen(false)} className="inline-flex h-9 items-center rounded-lg bg-slate-800 px-3 text-xs font-medium text-white hover:bg-slate-900">关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}











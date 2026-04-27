import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  CheckSquare,
  Eye,
  FileText,
  Loader2,
  RefreshCcw,
  Search,
  Square,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import * as adminIngestionApi from '../api/admin-ingestion'
import { extractApiErrorMessage } from '../api'
import DocumentPreviewFrame from '../components/documents/DocumentPreviewFrame'
import type { KnowledgePointResponse } from '../types'
import { useKnowledgeStore } from '../store'

const PAGE_SIZE = 20
const POLL_MAX_DURATION_MS = 5 * 60 * 1000
const POLL_STALE_PROGRESS_MS = 60 * 1000

const inferFileType = (file: File): string => {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (ext) return ext
  return file.type || 'txt'
}

const FILE_CONTENT_TYPE_MAP: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  txt: 'text/plain; charset=utf-8',
  md: 'text/markdown; charset=utf-8',
  html: 'text/html; charset=utf-8',
}

const resolveUploadContentType = (file: File, normalizedType: string): string => {
  const normalizedMimeType = file.type.split(';', 1)[0]?.trim()
  if (normalizedMimeType) return normalizedMimeType
  return FILE_CONTENT_TYPE_MAP[normalizedType] ?? 'application/octet-stream'
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const normalizeJobStatus = (status: string): 'pending' | 'running' | 'success' | 'failed' => {
  const normalized = status.trim().toLowerCase()
  if (normalized === 'success' || normalized === 'failed' || normalized === 'running') {
    return normalized
  }
  return 'pending'
}

export default function KnowledgeManagementPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadBatchTotal, setUploadBatchTotal] = useState(0)
  const [uploadCurrentIndex, setUploadCurrentIndex] = useState(0)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [batchReindexing, setBatchReindexing] = useState(false)
  const [batchDeleting, setBatchDeleting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())
  const [docDetailOpen, setDocDetailOpen] = useState(false)
  const [docDetailLoading, setDocDetailLoading] = useState(false)
  const [docDetail, setDocDetail] = useState<KnowledgePointResponse | null>(null)
  const [docPreviewUrl, setDocPreviewUrl] = useState('')
  const [docPreviewState, setDocPreviewState] = useState<adminIngestionApi.KnowledgePointPreviewState | null>(null)
  const [docPreviewStateMessage, setDocPreviewStateMessage] = useState('')
  const [docChunkSearch, setDocChunkSearch] = useState('')

  const pollRunIdRef = useRef(0)
  const pollAbortRef = useRef<AbortController | null>(null)
  const uploadStageTimerRef = useRef<number | null>(null)

  const {
    knowledgePoints,
    total,
    loading,
    page,
    pageSize,
    query,
    fetchKnowledgePoints,
    reindexKnowledgePoint,
    deleteKnowledgePoint,
  } = useKnowledgeStore()

  useEffect(() => {
    void fetchKnowledgePoints({ page: 1, pageSize: PAGE_SIZE, q: '' })
  }, [fetchKnowledgePoints])

  useEffect(() => {
    return () => {
      pollRunIdRef.current += 1
      pollAbortRef.current?.abort()
      pollAbortRef.current = null
      if (uploadStageTimerRef.current) {
        window.clearInterval(uploadStageTimerRef.current)
        uploadStageTimerRef.current = null
      }
    }
  }, [])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const allSelected = knowledgePoints.length > 0 && knowledgePoints.every((item) => selectedIds.has(item.id))

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (allSelected) return new Set()
      const next = new Set(prev)
      knowledgePoints.forEach((item) => next.add(item.id))
      return next
    })
  }

  const resetDocumentDetail = () => {
    setDocDetailOpen(false)
    setDocDetailLoading(false)
    setDocDetail(null)
    setDocPreviewUrl('')
    setDocPreviewState(null)
    setDocPreviewStateMessage('')
    setDocChunkSearch('')
  }

  const setDeletingState = (id: string, deleting: boolean) => {
    setDeletingIds((prev) => {
      const next = new Set(prev)
      if (deleting) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const updateBatchUploadProgress = (fileIndex: number, totalFiles: number, fileProgress: number) => {
    const normalizedTotal = Math.max(totalFiles, 1)
    const normalizedProgress = Math.max(0, Math.min(100, fileProgress))
    const overallProgress = ((fileIndex + normalizedProgress / 100) / normalizedTotal) * 100
    setUploadProgress((prev) => Math.max(prev, overallProgress))
  }

  const stopUploadStageTimer = () => {
    if (uploadStageTimerRef.current) {
      window.clearInterval(uploadStageTimerRef.current)
      uploadStageTimerRef.current = null
    }
  }

  const startUploadStageTimer = (fileIndex: number, totalFiles: number) => {
    stopUploadStageTimer()
    let stagedFileProgress = 5
    updateBatchUploadProgress(fileIndex, totalFiles, stagedFileProgress)
    uploadStageTimerRef.current = window.setInterval(() => {
      stagedFileProgress = Math.min(stagedFileProgress + 2, 40)
      updateBatchUploadProgress(fileIndex, totalFiles, stagedFileProgress)
    }, 300)
  }

  const pollIngestionJob = async (
    jobId: string,
    runId: number,
    signal: AbortSignal,
    onProgress?: (progress: number) => void
  ) => {
    const startedAt = Date.now()
    let waitMs = 1000
    let lastProgress = 0
    let lastProgressAt = Date.now()

    for (let i = 0; i < 150; i += 1) {
      if (pollRunIdRef.current !== runId || signal.aborted) {
        throw new Error('上传任务已取消')
      }

      const job = await adminIngestionApi.getIngestionJob(jobId, signal)
      const status = normalizeJobStatus(job.status)
      const currentProgress = Math.max(45, Math.min(99, job.progress))
      onProgress?.(currentProgress)

      if (currentProgress > lastProgress) {
        lastProgress = currentProgress
        lastProgressAt = Date.now()
      }

      if (status === 'success') return
      if (status === 'failed') {
        throw new Error(job.error_message || '解析失败')
      }

      if (Date.now() - startedAt > POLL_MAX_DURATION_MS) {
        throw new Error(`解析任务超时，请重试。任务ID：${jobId}`)
      }

      if (Date.now() - lastProgressAt > POLL_STALE_PROGRESS_MS) {
        const taskHint = job.celery_task_id ? `，Celery任务：${job.celery_task_id}` : ''
        throw new Error(`解析任务长时间无进度变化，可能是Worker异常。任务ID：${jobId}${taskHint}`)
      }

      await sleep(waitMs)
      waitMs = Math.min(2000, waitMs + 100)
    }

    throw new Error(`解析任务超时，请重试。任务ID：${jobId}`)
  }

  const uploadSingleFile = async (
    file: File,
    fileIndex: number,
    totalFiles: number,
    runId: number,
    signal: AbortSignal
  ) => {
    const normalizedType = inferFileType(file)

    startUploadStageTimer(fileIndex, totalFiles)
    try {
      updateBatchUploadProgress(fileIndex, totalFiles, 10)

      const presignResponse = await adminIngestionApi.presignUpload({
        file_name: file.name,
        file_type: normalizedType,
        file_size: file.size,
      })

      updateBatchUploadProgress(fileIndex, totalFiles, 20)

      const uploadResponse = await fetch(presignResponse.upload_url, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': resolveUploadContentType(file, normalizedType),
        },
        signal,
      })

      if (!uploadResponse.ok) {
        throw new Error('上传失败')
      }

      const callback = await adminIngestionApi.uploadCallback({
        object_path: presignResponse.object_path,
        file_name: file.name,
        file_type: normalizedType,
        file_size: file.size,
      })

      stopUploadStageTimer()
      updateBatchUploadProgress(fileIndex, totalFiles, 45)
      await pollIngestionJob(callback.job_id, runId, signal, (progress) => {
        updateBatchUploadProgress(fileIndex, totalFiles, progress)
      })
      updateBatchUploadProgress(fileIndex, totalFiles, 100)
    } finally {
      stopUploadStageTimer()
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isUploading) return

    const files = Array.from(e.target.files ?? [])
    if (files.length === 0) return

    pollRunIdRef.current += 1
    const currentRunId = pollRunIdRef.current

    pollAbortRef.current?.abort()
    pollAbortRef.current = new AbortController()

    const signal = pollAbortRef.current.signal
    setUploadFile(files[0])
    setUploadBatchTotal(files.length)
    setUploadCurrentIndex(0)
    setIsUploading(true)
    setUploadProgress(0)

    try {
      const succeededFiles: string[] = []
      const failedFiles: string[] = []

      for (const [index, file] of files.entries()) {
        if (pollRunIdRef.current !== currentRunId || signal.aborted) {
          throw new Error('上传任务已取消')
        }

        setUploadCurrentIndex(index)
        setUploadFile(file)

        try {
          await uploadSingleFile(file, index, files.length, currentRunId, signal)
          succeededFiles.push(file.name)
        } catch (error) {
          const message = error instanceof Error ? error.message : '文件上传失败'
          failedFiles.push(`${file.name}：${message}`)
          toast.error(`${file.name}：${message}`)
        }
      }

      if (succeededFiles.length > 0) {
        await fetchKnowledgePoints({ page: 1, pageSize, q: query })
      }

      if (failedFiles.length === 0) {
        toast.success(files.length === 1 ? '文档上传并解析完成' : `批量上传完成，共成功 ${succeededFiles.length} 份文档`)
      } else if (succeededFiles.length > 0) {
        toast.success(`批量上传部分完成，成功 ${succeededFiles.length} 份文档`)
        toast.error(`失败 ${failedFiles.length} 份文档，请查看逐条错误提示`)
      } else {
        toast.error(`批量上传失败，共 ${failedFiles.length} 份文档`)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '文件上传失败'
      toast.error(message)
    } finally {
      stopUploadStageTimer()

      window.setTimeout(() => {
        setIsUploading(false)
        setUploadFile(null)
        setUploadBatchTotal(0)
        setUploadCurrentIndex(0)
        setUploadProgress(0)
      }, 400)

      e.target.value = ''
    }
  }

  const handleReindex = async (id: string) => {
    try {
      const job = await reindexKnowledgePoint(id)
      toast.success(`重建索引任务已触发：${job.id}`)
    } catch {
      toast.error('重建索引失败')
    }
  }

  const handleBatchReindex = async () => {
    if (selectedIds.size === 0) {
      toast.error('请先选择要重建索引的知识点')
      return
    }

    setBatchReindexing(true)
    try {
      await Promise.all([...selectedIds].map(async (id) => reindexKnowledgePoint(id)))
      toast.success(`已触发 ${selectedIds.size} 条知识点重建索引`)
      setSelectedIds(new Set())
    } catch {
      toast.error('批量重建索引失败，请稍后重试')
    } finally {
      setBatchReindexing(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (deletingIds.has(id)) return

    const target = knowledgePoints.find((item) => item.id === id)
    const confirmed = window.confirm(
      `确认删除文档「${target?.title ?? '该知识点'}」？这会同时删除解析切片、向量数据、对象存储文件以及相关入库任务绑定。`
    )
    if (!confirmed) return

    setDeletingState(id, true)
    try {
      const result = await deleteKnowledgePoint(id)
      if (docDetail?.id === id) resetDocumentDetail()
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
      const nextPage = page > 1 && knowledgePoints.length === 1 ? page - 1 : page
      await fetchKnowledgePoints({ page: nextPage, pageSize, q: query })
      toast.success(`文档已删除，清理 ${result.deleted_chunk_count} 个切片`)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '删除文档失败'))
    } finally {
      setDeletingState(id, false)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) {
      toast.error('请先选择要删除的知识点')
      return
    }

    const ids = [...selectedIds]
    const confirmed = window.confirm(
      `确认删除选中的 ${ids.length} 份文档？这会同时删除对应切片、向量数据、对象存储文件以及相关入库任务绑定。`
    )
    if (!confirmed) return

    setBatchDeleting(true)
    ids.forEach((id) => setDeletingState(id, true))
    try {
      const results = await Promise.allSettled(ids.map(async (id) => ({ id, result: await deleteKnowledgePoint(id) })))
      const succeeded = results.filter(
        (
          item,
        ): item is PromiseFulfilledResult<{
          id: string
          result: Awaited<ReturnType<typeof deleteKnowledgePoint>>
        }> => item.status === 'fulfilled'
      )
      const failed = results.filter((item) => item.status === 'rejected')

      if (succeeded.length > 0) {
        const deletedChunkCount = succeeded.reduce((sum, item) => sum + item.value.result.deleted_chunk_count, 0)
        if (docDetail && succeeded.some((item) => item.value.id === docDetail.id)) {
          resetDocumentDetail()
        }
        setSelectedIds(new Set())
        const nextPage = page > 1 && succeeded.length >= knowledgePoints.length ? page - 1 : page
        await fetchKnowledgePoints({ page: nextPage, pageSize, q: query })
        toast.success(`已删除 ${succeeded.length} 份文档，清理 ${deletedChunkCount} 个切片`)
      }

      if (failed.length > 0) {
        toast.error(`有 ${failed.length} 份文档删除失败，请重试`)
      }
    } finally {
      ids.forEach((id) => setDeletingState(id, false))
      setBatchDeleting(false)
    }
  }

  const handleSearch = async () => {
    await fetchKnowledgePoints({ page: 1, pageSize, q: searchTerm.trim() })
  }

  const openDocumentDetail = async (id: string) => {
    setDocDetailOpen(true)
    setDocDetailLoading(true)
    setDocChunkSearch('')
    try {
      const [detail, preview] = await Promise.all([
        adminIngestionApi.getKnowledgePoint(id),
        adminIngestionApi.getKnowledgePointDocumentUrl(id),
      ])
      setDocDetail(detail)
      const resolvedPreview = adminIngestionApi.resolveKnowledgePointDocumentPreview(preview)
      setDocPreviewUrl(resolvedPreview.url)
      setDocPreviewState(resolvedPreview.state)
      setDocPreviewStateMessage(resolvedPreview.stateMessage)
    } catch (error) {
      resetDocumentDetail()
      toast.error(extractApiErrorMessage(error, '文档详情加载失败'))
    } finally {
      setDocDetailLoading(false)
    }
  }

  const filteredDocChunks = useMemo(() => {
    if (!docDetail) return []
    const query = docChunkSearch.trim().toLowerCase()
    const chunks = [...docDetail.chunks].sort((a, b) => a.chunk_index - b.chunk_index)
    if (!query) return chunks
    return chunks.filter((item) => item.content.toLowerCase().includes(query))
  }, [docDetail, docChunkSearch])

  const pageLabel = useMemo(() => `第 ${page} / ${totalPages} 页`, [page, totalPages])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">知识库管理</h1>
          <p className="mt-1 text-sm text-slate-500">管理文档上传、检索索引与知识点生命周期。</p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            type="file"
            id="file-upload"
            className="hidden"
            onChange={handleFileUpload}
            accept=".pdf,.docx,.pptx,.md,.html,.txt"
            multiple
            disabled={isUploading}
          />

          <label
            htmlFor="file-upload"
            className={`inline-flex h-11 cursor-pointer items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition-all ${
              isUploading
                ? 'pointer-events-none bg-slate-200 text-slate-500'
                : 'bg-gradient-to-r from-indigo-500 to-indigo-600 text-white shadow-lg shadow-indigo-500/25 hover:-translate-y-0.5 hover:from-indigo-600 hover:to-indigo-700'
            }`}
          >
            {isUploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                上传中...
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                上传文档 / 批量上传
              </>
            )}
          </label>

          <button
            onClick={() => void handleBatchReindex()}
            disabled={batchReindexing || batchDeleting || selectedIds.size === 0}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 transition-all hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {batchReindexing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            批量重建索引
          </button>
          <button
            onClick={() => void handleBatchDelete()}
            disabled={batchDeleting || batchReindexing || selectedIds.size === 0}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-red-200 bg-white px-4 text-sm font-medium text-red-600 transition-all hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {batchDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            批量删除
          </button>
        </div>
      </div>

      {isUploading && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-medium text-indigo-700">
              处理中：{uploadFile?.name}
              {uploadBatchTotal > 1 ? `（${uploadCurrentIndex + 1}/${uploadBatchTotal}）` : ''}
            </span>
            <span className="text-indigo-600">{Math.round(uploadProgress)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-indigo-100">
            <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all" style={{ width: `${uploadProgress}%` }} />
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full lg:max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="搜索知识点标题"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleSearch()
                }}
                className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100"
              />
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => void handleSearch()}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
              >
                查询
              </button>
              <div className="inline-flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
                <span>总计 {total}</span>
                <span>·</span>
                <span>{pageLabel}</span>
                <span>·</span>
                <span>已选择 {selectedIds.size}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="divide-y divide-slate-200">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-4">
                <div className="h-4 w-4 animate-pulse rounded bg-slate-100" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-1/3 animate-pulse rounded bg-slate-100" />
                  <div className="h-3 w-1/4 animate-pulse rounded bg-slate-100" />
                </div>
              </div>
            ))
          ) : knowledgePoints.length === 0 ? (
            <div className="p-14 text-center">
              <FileText className="mx-auto mb-4 h-12 w-12 text-slate-300" />
              <p className="text-sm font-medium text-slate-500">暂无知识点</p>
              <p className="mt-1 text-xs text-slate-400">上传文档后系统会自动解析并生成知识点。</p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase tracking-wider text-slate-500">
                <button onClick={toggleSelectAll} className="inline-flex items-center gap-1 text-slate-600">
                  {allSelected ? <CheckSquare className="h-4 w-4 text-indigo-500" /> : <Square className="h-4 w-4" />}
                  全选
                </button>
                <span className="w-24">类型</span>
                <span className="flex-1">标题</span>
                <span className="hidden w-40 md:block">创建时间</span>
                <span className="w-24 text-center">状态</span>
                <span className="w-24 text-right">操作</span>
              </div>

              {knowledgePoints.map((point, index) => (
                <motion.div
                  key={point.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.03 }}
                  className={`flex items-center gap-3 px-4 py-3 transition-colors hover:bg-indigo-50/40 ${
                    index % 2 === 1 ? 'bg-slate-50/45' : 'bg-white'
                  }`}
                >
                  <button onClick={() => toggleSelect(point.id)}>
                    {selectedIds.has(point.id) ? (
                      <CheckSquare className="h-4 w-4 text-indigo-500" />
                    ) : (
                      <Square className="h-4 w-4 text-slate-400" />
                    )}
                  </button>

                  <div className="w-24 text-xs text-slate-500">{point.file_type}</div>

                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => void openDocumentDetail(point.id)}
                      className="max-w-full truncate text-left text-sm font-medium text-slate-800 underline-offset-2 hover:text-indigo-600 hover:underline"
                    >
                      {point.title}
                    </button>
                    <p className="mt-1 truncate text-xs text-slate-400">{point.object_path}</p>
                  </div>

                  <div className="hidden w-40 text-xs text-slate-500 md:block">{new Date(point.created_at).toLocaleString()}</div>

                  <div className="w-24 text-center">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                        point.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {point.is_active ? '启用' : '停用'}
                    </span>
                  </div>

                  <div className="flex w-32 justify-end gap-2">
                    <button
                      onClick={() => void openDocumentDetail(point.id)}
                      className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-indigo-100 hover:text-indigo-600"
                      title="查看文档"
                    >
                      <Eye className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => void handleReindex(point.id)}
                      disabled={deletingIds.has(point.id)}
                      className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-indigo-100 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
                      title="重建索引"
                    >
                      <RefreshCcw className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => void handleDelete(point.id)}
                      disabled={deletingIds.has(point.id)}
                      className="rounded-lg p-1.5 text-red-500 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      title="删除文档"
                    >
                      {deletingIds.has(point.id) ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </button>
                  </div>
                </motion.div>
              ))}
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3">
          <span className="text-xs text-slate-500">共 {total} 条记录</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void fetchKnowledgePoints({ page: Math.max(1, page - 1), pageSize, q: query })}
              disabled={page <= 1}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition-colors hover:border-slate-300 disabled:opacity-50"
            >
              上一页
            </button>
            <span className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white">{page}</span>
            <button
              onClick={() => void fetchKnowledgePoints({ page: Math.min(totalPages, page + 1), pageSize, q: query })}
              disabled={page >= totalPages}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition-colors hover:border-slate-300 disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      </div>

      {docDetailOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 p-4 backdrop-blur-sm">
          <div className="h-[86vh] w-full max-w-7xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.08em] text-slate-500">文档详情</p>
                <h3 className="text-sm font-semibold text-slate-800">{docDetail?.title || '加载中...'}</h3>
              </div>
              <div className="flex items-center gap-2">
                {docDetail && (
                  <button
                    onClick={() => void handleDelete(docDetail.id)}
                    disabled={deletingIds.has(docDetail.id)}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-2.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {deletingIds.has(docDetail.id) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                    删除
                  </button>
                )}
                <button onClick={resetDocumentDetail} className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-700">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {docDetailLoading ? (
              <div className="flex h-[calc(86vh-57px)] items-center justify-center gap-2 text-sm text-slate-600">
                <Loader2 className="h-4 w-4 animate-spin" /> 文档详情加载中...
              </div>
            ) : (
              <div className="grid h-[calc(86vh-57px)] grid-cols-1 gap-0 lg:grid-cols-[0.95fr_1.05fr]">
                <section className="min-h-0 border-b border-slate-200 bg-slate-50/70 p-4 lg:border-b-0 lg:border-r">
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-slate-800">解析内容（Chunks）</h4>
                    <span className="text-xs text-slate-500">{filteredDocChunks.length} 条</span>
                  </div>
                  <input
                    value={docChunkSearch}
                    onChange={(e) => setDocChunkSearch(e.target.value)}
                    placeholder="搜索 chunk 内容"
                    className="mb-3 h-9 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                  />
                  <div className="h-[calc(100%-70px)] space-y-2 overflow-auto pr-1">
                    {filteredDocChunks.length === 0 ? (
                      <div className="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-500">暂无匹配内容</div>
                    ) : (
                      filteredDocChunks.map((chunk) => (
                        <article key={chunk.id} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                          <p className="mb-1 text-[11px] font-semibold tracking-[0.06em] text-indigo-600">CHUNK #{chunk.chunk_index}</p>
                          <p className="whitespace-pre-wrap text-xs leading-6 text-slate-700">{chunk.content}</p>
                        </article>
                      ))
                    )}
                  </div>
                </section>

                <section className="flex min-h-0 flex-col bg-slate-100 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-slate-800">统一文档预览</h4>
                    {docPreviewUrl && (
                      <a
                        href={docPreviewUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
                      >
                        新窗口打开
                      </a>
                    )}
                  </div>
                  <DocumentPreviewFrame
                    previewUrl={docPreviewUrl}
                    previewState={docPreviewState}
                    previewStateMessage={docPreviewStateMessage}
                  />
                </section>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

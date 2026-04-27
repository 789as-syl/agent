import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  CheckSquare,
  Database,
  Download,
  Edit3,
  FileQuestion,
  Link2,
  Loader2,
  Plus,
  Search,
  Square,
  Trash2,
  Upload,
  X,
} from 'lucide-react'

import * as adminQuestionsApi from '../api/admin-questions'
import { extractApiErrorMessage } from '../api'
import QuestionEditorModal from '../components/questions/QuestionEditorModal'
import {
  buildQuestionWritePayload,
  createEmptyQuestionEditorState,
  formatQuestionAnswer,
  questionToEditorState,
  type QuestionEditorFormState,
} from '../components/questions/questionEditorUtils'
import { useQuestionManagementActions } from '../hooks/useQuestionManagementActions'
import { useKnowledgeCandidates } from '../hooks/useKnowledgeCandidates'
import { useQuestionManagementFilters } from '../hooks/useQuestionManagementFilters'
import { useVectorizationJobPolling } from '../hooks/useVectorizationJobPolling'
import { useQuestionStore } from '../store'
import type { QuestionResponse, QuestionType } from '../types'

const PAGE_SIZE = 20

const questionTypeLabelMap: Record<QuestionType, string> = {
  single: '单选题',
  multiple: '多选题',
  true_false: '判断题',
  short_answer: '简答题',
}

export default function QuestionManagementPage() {
  const [createQuestionOpen, setCreateQuestionOpen] = useState(false)
  const [questionSaving, setQuestionSaving] = useState(false)
  const [createQuestionState, setCreateQuestionState] = useState<QuestionEditorFormState>(() =>
    createEmptyQuestionEditorState()
  )
  const [newQuestionKnowledgeSearch, setNewQuestionKnowledgeSearch] = useState('')
  const [newQuestionKnowledgeIds, setNewQuestionKnowledgeIds] = useState<Set<string>>(new Set())

  const [mappingQuestion, setMappingQuestion] = useState<QuestionResponse | null>(null)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [mappingSaving, setMappingSaving] = useState(false)
  const [knowledgeSearch, setKnowledgeSearch] = useState('')
  const [selectedKnowledgeIds, setSelectedKnowledgeIds] = useState<Set<string>>(new Set())

  const [editingQuestion, setEditingQuestion] = useState<QuestionResponse | null>(null)
  const [editQuestionOpen, setEditQuestionOpen] = useState(false)
  const [editQuestionSaving, setEditQuestionSaving] = useState(false)
  const [editKnowledgeSearch, setEditKnowledgeSearch] = useState('')
  const [editKnowledgeIds, setEditKnowledgeIds] = useState<Set<string>>(new Set())
  const [editQuestionState, setEditQuestionState] = useState<QuestionEditorFormState>(() =>
    createEmptyQuestionEditorState()
  )

  const {
    questions,
    questionBanks,
    total,
    loading,
    page,
    pageSize,
    fetchQuestions,
    fetchQuestionBanks,
    deleteQuestion,
    importQuestions,
    vectorizeQuestions,
  } = useQuestionStore()
  const pollVectorizationJob = useVectorizationJobPolling(adminQuestionsApi.getVectorizationJob)
  const {
    searchTerm,
    setSearchTerm,
    questionType,
    setQuestionType,
    dirtyFilter,
    setDirtyFilter,
    selectedBankId,
    setSelectedBankId,
    selectedIds,
    setSelectedIds,
    totalPages,
    allSelected,
    selectedBank,
    runSearch,
    toggleSelect,
    toggleSelectAll,
  } = useQuestionManagementFilters({
    questions,
    total,
    page,
    pageSize,
    questionBanks,
    fetchQuestions,
  })
  const { knowledgeCandidates, knowledgeLoading, loadKnowledgeCandidates } = useKnowledgeCandidates({
    onError: (message) => toast.error(message),
  })
  const {
    isVectorizing,
    isImporting,
    createBankOpen,
    editBankOpen,
    bankSaving,
    bankName,
    bankDescription,
    setCreateBankOpen,
    setEditBankOpen,
    setBankName,
    setBankDescription,
    handleDelete,
    handleBatchDelete,
    handleVectorize,
    handleFileImport,
    openCreateBank,
    openEditBank,
    handleCreateBank,
    handleUpdateBank,
    handleDeleteBank,
  } = useQuestionManagementActions({
    deleteQuestion,
    importQuestions,
    vectorizeQuestions,
    pollVectorizationJob,
    fetchQuestionBanks,
    runSearch,
    setSelectedBankId,
    setSelectedIds,
    selectedIds,
    selectedBankId,
    selectedBank,
    page,
  })

  useEffect(() => {
    const run = async () => {
      await fetchQuestionBanks()
      await fetchQuestions({ page: 1, pageSize: PAGE_SIZE })
    }
    void run()
  }, [fetchQuestionBanks, fetchQuestions])

  const dirtyCount = questions.filter((item) => item.is_dirty).length

  const openCreateQuestion = async () => {
    if (!selectedBankId) {
      toast.error('请先选择题库，再创建题目')
      return
    }

    setCreateQuestionState(createEmptyQuestionEditorState())
    setNewQuestionKnowledgeSearch('')
    setNewQuestionKnowledgeIds(new Set())
    setCreateQuestionOpen(true)
    await loadKnowledgeCandidates()
  }

  const handleCreateQuestion = async () => {
    if (!selectedBankId) {
      toast.error('请先选择题库')
      return
    }

    const result = buildQuestionWritePayload(createQuestionState)
    if (result.error || !result.payload) {
      toast.error(result.error ?? '题目参数不完整')
      return
    }

    setQuestionSaving(true)
    try {
      await adminQuestionsApi.createQuestion({
        bank_id: selectedBankId,
        ...result.payload,
        knowledge_point_ids: [...newQuestionKnowledgeIds],
      })
      setCreateQuestionOpen(false)
      toast.success('题目创建成功')
      await runSearch(1)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '题目创建失败'))
    } finally {
      setQuestionSaving(false)
    }
  }

  const openMappingDialog = async (question: QuestionResponse) => {
    setMappingQuestion(question)
    setMappingOpen(true)
    setKnowledgeSearch('')
    setSelectedKnowledgeIds(new Set(question.knowledge_point_ids || []))
    await loadKnowledgeCandidates()
  }

  const handleSaveMapping = async () => {
    if (!mappingQuestion) return
    setMappingSaving(true)
    try {
      await adminQuestionsApi.linkKnowledgePoints(mappingQuestion.id, {
        knowledge_point_ids: [...selectedKnowledgeIds],
      })
      setMappingOpen(false)
      toast.success('题目知识点关系已更新')
      await runSearch(page)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '保存关系失败'))
    } finally {
      setMappingSaving(false)
    }
  }

  const openEditQuestion = async (question: QuestionResponse) => {
    setEditingQuestion(question)
    setEditQuestionState(questionToEditorState(question))
    setEditKnowledgeIds(new Set(question.knowledge_point_ids ?? []))
    setEditKnowledgeSearch('')
    setEditQuestionOpen(true)
    await loadKnowledgeCandidates()
  }

  const handleSaveEditQuestion = async () => {
    if (!editingQuestion) return

    const result = buildQuestionWritePayload(editQuestionState)
    if (result.error || !result.payload) {
      toast.error(result.error ?? '题目参数不完整')
      return
    }

    setEditQuestionSaving(true)
    try {
      await adminQuestionsApi.updateQuestion(editingQuestion.id, result.payload)
      await adminQuestionsApi.linkKnowledgePoints(editingQuestion.id, {
        knowledge_point_ids: [...editKnowledgeIds],
      })
      setEditQuestionOpen(false)
      setEditingQuestion(null)
      toast.success('题目编辑成功')
      await runSearch(page)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '题目编辑失败'))
    } finally {
      setEditQuestionSaving(false)
    }
  }

  const filteredKnowledgePoints = useMemo(() => {
    const q = knowledgeSearch.trim().toLowerCase()
    if (!q) return knowledgeCandidates
    return knowledgeCandidates.filter((item) => item.title.toLowerCase().includes(q))
  }, [knowledgeCandidates, knowledgeSearch])

  const filteredKnowledgePointsForCreate = useMemo(() => {
    const q = newQuestionKnowledgeSearch.trim().toLowerCase()
    if (!q) return knowledgeCandidates
    return knowledgeCandidates.filter((item) => item.title.toLowerCase().includes(q))
  }, [knowledgeCandidates, newQuestionKnowledgeSearch])

  const filteredKnowledgePointsForEdit = useMemo(() => {
    const q = editKnowledgeSearch.trim().toLowerCase()
    if (!q) return knowledgeCandidates
    return knowledgeCandidates.filter((item) => item.title.toLowerCase().includes(q))
  }, [knowledgeCandidates, editKnowledgeSearch])

  const pageLabel = useMemo(() => `第 ${page} / ${totalPages} 页`, [page, totalPages])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">题库管理</h1>
          <p className="mt-1 text-sm text-slate-500">维护题目数据、知识点关联与向量化状态。</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="file"
            id="question-import"
            className="hidden"
            accept=".json,.xlsx"
            onChange={handleFileImport}
            disabled={!selectedBankId || isImporting}
          />
          <label
            htmlFor="question-import"
            className={`inline-flex h-11 cursor-pointer items-center gap-2 rounded-xl px-4 text-sm font-medium transition-all ${
              !selectedBankId
                ? 'cursor-not-allowed bg-slate-100 text-slate-400'
                : isImporting
                  ? 'bg-slate-200 text-slate-500'
                  : 'border border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:text-indigo-600'
            }`}
          >
            {isImporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            批量导入
          </label>
          <button
            onClick={() => void handleVectorize()}
            disabled={isVectorizing}
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 transition-all hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isVectorizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
            触发向量化
          </button>
          <button
            onClick={() => void openCreateQuestion()}
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600 transition-all hover:border-indigo-200 hover:text-indigo-600"
          >
            <Plus className="h-4 w-4" />创建题目
          </button>
          <button
            onClick={openCreateBank}
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 px-4 text-sm font-medium text-white shadow-lg shadow-indigo-500/20 transition-all hover:-translate-y-0.5 hover:from-indigo-600 hover:to-indigo-700"
          >
            <Plus className="h-4 w-4" />新建题库
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 text-xs leading-5 text-amber-700">
        当前页题目 <span className="font-semibold">{questions.length}</span>，待向量化 <span className="font-semibold">{dirtyCount}</span>。
        <br />
        当前录题/改题/导题统一规则：单选/多选仅支持 A/B/C/D；判断题答案统一保存为 true/false；批量导入支持 JSON / Excel（.xlsx），并严格校验新模板，非法行跳过。
        <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
          <a
            href="/examples/admin-question-import-sample.json"
            download
            className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-white px-2.5 py-1 font-medium text-amber-700 hover:border-amber-300"
          >
            <Download className="h-3.5 w-3.5" />
            下载合法示例 JSON
          </a>
          <a
            href="/examples/admin-question-import-mixed-invalid.json"
            download
            className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-white px-2.5 py-1 font-medium text-amber-700 hover:border-amber-300"
          >
            <Download className="h-3.5 w-3.5" />
            下载混合校验示例
          </a>
          <a
            href="/examples/admin-question-import-sample.xlsx"
            download
            className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-white px-2.5 py-1 font-medium text-amber-700 hover:border-amber-300"
          >
            <Download className="h-3.5 w-3.5" />
            下载合法示例 Excel
          </a>
          <span className="inline-flex items-center rounded-full border border-amber-200 bg-white px-2.5 py-1 text-amber-700">
            JSON 示例导入前请先将 bank_id 替换为当前题库 ID；Excel 示例会导入到当前所选题库
          </span>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center lg:max-w-4xl">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="搜索题目内容"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void runSearch(1)
                  }}
                  className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100"
                />
              </div>
              <select
                value={selectedBankId}
                onChange={(e) => setSelectedBankId(e.target.value)}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-600 outline-none transition-all focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
              >
                <option value="">全部题库</option>
                {questionBanks.map((bank) => (
                  <option key={bank.id} value={bank.id}>
                    {bank.name}
                  </option>
                ))}
              </select>
              <button
                onClick={() => selectedBank && openEditBank(selectedBank)}
                disabled={!selectedBank}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-600 hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                编辑题库
              </button>
              <button
                onClick={() => void handleDeleteBank()}
                disabled={!selectedBank}
                className="h-10 rounded-xl border border-red-200 bg-white px-3 text-sm text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                删除题库
              </button>
              <select
                value={questionType}
                onChange={(e) => setQuestionType(e.target.value)}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-600 outline-none transition-all focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
              >
                <option value="all">全部类型</option>
                <option value="single">单选题</option>
                <option value="multiple">多选题</option>
                <option value="true_false">判断题</option>
                <option value="short_answer">简答题</option>
              </select>
              <select
                value={dirtyFilter}
                onChange={(e) => setDirtyFilter(e.target.value as 'all' | 'dirty' | 'clean')}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-600 outline-none transition-all focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
              >
                <option value="all">全部状态</option>
                <option value="dirty">待向量化</option>
                <option value="clean">已向量化</option>
              </select>
              <button
                onClick={() => void runSearch(1)}
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
              >
                查询
              </button>
            </div>
            <div className="inline-flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
              <span>总计 {total}</span>
              <span>·</span>
              <span>{pageLabel}</span>
              <span>·</span>
              <span>已选择 {selectedIds.size}</span>
            </div>
          </div>
          {selectedIds.size > 0 && (
            <div className="mt-3 flex items-center justify-between rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
              <span>已选择 {selectedIds.size} 道题目</span>
              <button
                onClick={() => void handleBatchDelete()}
                className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 font-medium text-red-600 hover:bg-red-50"
              >
                <Trash2 className="h-3.5 w-3.5" />批量删除
              </button>
            </div>
          )}
        </div>
        <div className="divide-y divide-slate-200">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-4">
                <div className="h-4 w-4 animate-pulse rounded bg-slate-100" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
                  <div className="h-3 w-1/3 animate-pulse rounded bg-slate-100" />
                </div>
              </div>
            ))
          ) : questions.length === 0 ? (
            <div className="p-14 text-center">
              <FileQuestion className="mx-auto mb-4 h-12 w-12 text-slate-300" />
              <p className="text-sm font-medium text-slate-500">暂无题目</p>
              <p className="mt-1 text-xs text-slate-400">可按题库导入 JSON/Excel。</p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase tracking-wider text-slate-500">
                <button onClick={toggleSelectAll} className="inline-flex items-center gap-1 text-slate-600">
                  {allSelected ? <CheckSquare className="h-4 w-4 text-indigo-500" /> : <Square className="h-4 w-4" />}全选
                </button>
                <span className="w-20">类型</span>
                <span className="flex-1">题干</span>
                <span className="hidden w-24 md:block">状态</span>
                <span className="hidden w-36 md:block">创建时间</span>
                <span className="w-32 text-right">操作</span>
              </div>
              {questions.map((question, index) => {
                const answerLabel = formatQuestionAnswer(question)
                return (
                  <motion.div
                    key={question.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.03 }}
                    className={`flex items-start gap-3 px-4 py-3 transition-colors hover:bg-indigo-50/40 ${
                      index % 2 === 1 ? 'bg-slate-50/45' : 'bg-white'
                    }`}
                  >
                    <button onClick={() => toggleSelect(question.id)} className="mt-0.5">
                      {selectedIds.has(question.id) ? (
                        <CheckSquare className="h-4 w-4 text-indigo-500" />
                      ) : (
                        <Square className="h-4 w-4 text-slate-400" />
                      )}
                    </button>
                    <div className="w-20 pt-0.5">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          question.question_type === 'single'
                            ? 'bg-indigo-50 text-indigo-600'
                            : question.question_type === 'multiple'
                              ? 'bg-violet-50 text-violet-600'
                              : question.question_type === 'true_false'
                                ? 'bg-emerald-50 text-emerald-600'
                                : 'bg-amber-50 text-amber-600'
                        }`}
                      >
                        {questionTypeLabelMap[question.question_type]}
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-sm font-medium text-slate-800">{question.question_text}</p>
                      {answerLabel && <p className="mt-1 line-clamp-1 text-xs text-slate-500">答案：{answerLabel}</p>}
                    </div>
                    <div className="hidden w-24 pt-0.5 text-xs md:block">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 font-medium ${
                          question.is_dirty ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'
                        }`}
                      >
                        {question.is_dirty ? '待向量化' : '已向量化'}
                      </span>
                    </div>
                    <div className="hidden w-36 pt-0.5 text-xs text-slate-500 md:block">
                      {new Date(question.created_at).toLocaleDateString()}
                    </div>
                    <div className="flex w-32 justify-end gap-1">
                      <button
                        onClick={() => void openMappingDialog(question)}
                        className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-indigo-100 hover:text-indigo-700"
                        title="知识点绑定"
                      >
                        <Link2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => void openEditQuestion(question)}
                        className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700"
                        title="编辑题目"
                      >
                        <Edit3 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => void handleDelete(question.id)}
                        className="rounded-lg p-1.5 text-red-500 transition-colors hover:bg-red-50"
                        title="删除"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </motion.div>
                )
              })}
            </>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3">
          <span className="text-xs text-slate-500">共 {total} 条记录</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void runSearch(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition-colors hover:border-slate-300 disabled:opacity-50"
            >
              上一页
            </button>
            <button className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white">{page}</button>
            <button
              onClick={() => void runSearch(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition-colors hover:border-slate-300 disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      </div>

      {(createBankOpen || editBankOpen) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900">{createBankOpen ? '新建题库' : '编辑题库'}</h3>
              <button
                onClick={() => {
                  setCreateBankOpen(false)
                  setEditBankOpen(false)
                }}
              >
                <X className="h-4 w-4 text-slate-500" />
              </button>
            </div>
            <div className="space-y-3">
              <input
                value={bankName}
                onChange={(e) => setBankName(e.target.value)}
                placeholder="题库名称"
                className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
              />
              <textarea
                value={bankDescription}
                onChange={(e) => setBankDescription(e.target.value)}
                placeholder="题库描述（可选）"
                rows={4}
                className="w-full rounded-xl border border-slate-200 p-3 text-sm"
              />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                onClick={() => {
                  setCreateBankOpen(false)
                  setEditBankOpen(false)
                }}
              >
                取消
              </button>
              <button
                disabled={bankSaving}
                className="rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-60"
                onClick={() => void (createBankOpen ? handleCreateBank() : handleUpdateBank())}
              >
                {bankSaving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {mappingOpen && mappingQuestion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-5 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900">知识点绑定</h3>
              <button onClick={() => setMappingOpen(false)}>
                <X className="h-4 w-4 text-slate-500" />
              </button>
            </div>
            <p className="mb-3 line-clamp-2 text-sm text-slate-600">{mappingQuestion.question_text}</p>
            <input
              value={knowledgeSearch}
              onChange={(e) => setKnowledgeSearch(e.target.value)}
              placeholder="搜索知识点"
              className="mb-3 h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
            />
            <div className="max-h-72 overflow-y-auto rounded-xl border border-slate-200 p-2">
              {knowledgeLoading ? (
                <div className="p-4 text-center text-sm text-slate-500">加载中...</div>
              ) : filteredKnowledgePoints.length === 0 ? (
                <div className="p-4 text-center text-sm text-slate-500">暂无知识点</div>
              ) : (
                filteredKnowledgePoints.map((item) => {
                  const checked = selectedKnowledgeIds.has(item.id)
                  return (
                    <label key={item.id} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 hover:bg-slate-50">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          setSelectedKnowledgeIds((prev) => {
                            const next = new Set(prev)
                            if (next.has(item.id)) next.delete(item.id)
                            else next.add(item.id)
                            return next
                          })
                        }}
                      />
                      <span className="text-sm text-slate-700">{item.title}</span>
                    </label>
                  )
                })
              )}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button className="rounded-lg border border-slate-200 px-3 py-2 text-sm" onClick={() => setMappingOpen(false)}>
                取消
              </button>
              <button
                onClick={() => void handleSaveMapping()}
                disabled={mappingSaving}
                className="rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-60"
              >
                {mappingSaving ? '保存中...' : '保存关系'}
              </button>
            </div>
          </div>
        </div>
      )}

      <QuestionEditorModal
        title="创建题目"
        open={createQuestionOpen}
        saving={questionSaving}
        state={createQuestionState}
        onChange={setCreateQuestionState}
        onClose={() => setCreateQuestionOpen(false)}
        onSubmit={() => void handleCreateQuestion()}
        submitLabel="创建题目"
        knowledgeSearch={newQuestionKnowledgeSearch}
        onKnowledgeSearchChange={setNewQuestionKnowledgeSearch}
        knowledgeLoading={knowledgeLoading}
        knowledgeCandidates={filteredKnowledgePointsForCreate}
        selectedKnowledgeIds={newQuestionKnowledgeIds}
        onToggleKnowledgeId={(id) => {
          setNewQuestionKnowledgeIds((prev) => {
            const next = new Set(prev)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
          })
        }}
      />

      <QuestionEditorModal
        title="编辑题目"
        open={editQuestionOpen && !!editingQuestion}
        saving={editQuestionSaving}
        state={editQuestionState}
        onChange={setEditQuestionState}
        onClose={() => {
          setEditQuestionOpen(false)
          setEditingQuestion(null)
        }}
        onSubmit={() => void handleSaveEditQuestion()}
        submitLabel="保存修改"
        knowledgeSearch={editKnowledgeSearch}
        onKnowledgeSearchChange={setEditKnowledgeSearch}
        knowledgeLoading={knowledgeLoading}
        knowledgeCandidates={filteredKnowledgePointsForEdit}
        selectedKnowledgeIds={editKnowledgeIds}
        onToggleKnowledgeId={(id) => {
          setEditKnowledgeIds((prev) => {
            const next = new Set(prev)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
          })
        }}
      />
    </div>
  )
}

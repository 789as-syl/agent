import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Eye, Loader2, Save, Search, Trash2, X } from 'lucide-react'

import type { GraphNode, KnowledgePointResponse, QuestionType } from '../types'
import {
  QUESTION_OPTION_LABELS,
  changeEditorType,
  type QuestionEditorFormState,
  type QuestionOptionLabel,
} from './questions/questionEditorUtils'

interface NodeDetailModalProps {
  open: boolean
  selectedNode: GraphNode | null
  detailLoading: boolean
  detailError: string | null
  selectedNodeConnections: number
  knowledgePointDetail: KnowledgePointResponse | null
  questionForm: QuestionEditorFormState
  questionTypeOptions: Array<{ label: string; value: QuestionType }>
  questionEditMode: boolean
  questionSaving: boolean
  knowledgePointCandidates: KnowledgePointResponse[]
  selectedKnowledgeIds: Set<string>
  chunkSearch: string
  filteredChunks: KnowledgePointResponse['chunks']
  visibleChunks: KnowledgePointResponse['chunks']
  showAllChunks: boolean
  documentLoading: boolean
  knowledgeSearch: string
  deletingKnowledgePoint: boolean
  onClose: () => void
  onOpenDocumentPreview: () => void
  onDeleteKnowledgePoint: () => void
  onToggleQuestionEdit: () => void
  onChunkSearchChange: (value: string) => void
  onKnowledgeSearchChange: (value: string) => void
  onToggleShowAllChunks: () => void
  onQuestionFormChange: (state: QuestionEditorFormState) => void
  onToggleKnowledgeSelection: (id: string, checked: boolean) => void
  onSaveQuestion: () => void
}

const getAnswerPreview = (state: QuestionEditorFormState): string => {
  if (state.questionType === 'single') {
    return state.singleAnswer || '未设置'
  }
  if (state.questionType === 'multiple') {
    return state.multipleAnswers.length > 0 ? state.multipleAnswers.join('、') : '未设置'
  }
  if (state.questionType === 'true_false') {
    if (state.trueFalseAnswer === 'true') return '对'
    if (state.trueFalseAnswer === 'false') return '错'
    return '未设置'
  }

  return state.shortAnswer.trim() || '未设置'
}

export default function NodeDetailModal({
  open,
  selectedNode,
  detailLoading,
  detailError,
  selectedNodeConnections,
  knowledgePointDetail,
  questionForm,
  questionTypeOptions,
  questionEditMode,
  questionSaving,
  knowledgePointCandidates,
  selectedKnowledgeIds,
  chunkSearch,
  filteredChunks,
  visibleChunks,
  showAllChunks,
  documentLoading,
  knowledgeSearch,
  deletingKnowledgePoint,
  onClose,
  onOpenDocumentPreview,
  onDeleteKnowledgePoint,
  onToggleQuestionEdit,
  onChunkSearchChange,
  onKnowledgeSearchChange,
  onToggleShowAllChunks,
  onQuestionFormChange,
  onToggleKnowledgeSelection,
  onSaveQuestion,
}: NodeDetailModalProps) {
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, onClose])

  if (!open || !selectedNode) return null

  const nodeTypeLabel =
    selectedNode.node_type === 'knowledge_point'
      ? '知识点'
      : selectedNode.is_orphan
        ? '题目（未关联）'
        : '题目'

  const nodeTypeTagClass =
    selectedNode.node_type === 'knowledge_point'
      ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
      : selectedNode.is_orphan
        ? 'border-amber-200 bg-amber-50 text-amber-700'
        : 'border-emerald-200 bg-emerald-50 text-emerald-700'

  const nodeAccentClass =
    selectedNode.node_type === 'knowledge_point'
      ? 'from-indigo-500 to-violet-500'
      : selectedNode.is_orphan
        ? 'from-amber-500 to-orange-500'
        : 'from-emerald-500 to-teal-500'

  const linkedKnowledgeTitle = knowledgePointCandidates
    .filter((item) => selectedKnowledgeIds.has(item.id))
    .map((item) => item.title)

  const handleOptionTextChange = (label: QuestionOptionLabel, value: string) => {
    const nextState: QuestionEditorFormState = {
      ...questionForm,
      optionTexts: {
        ...questionForm.optionTexts,
        [label]: value,
      },
    }

    if (!value.trim()) {
      if (questionForm.singleAnswer === label) {
        nextState.singleAnswer = ''
      }
      if (questionForm.multipleAnswers.includes(label)) {
        nextState.multipleAnswers = questionForm.multipleAnswers.filter((item) => item !== label)
      }
    }

    onQuestionFormChange(nextState)
  }

  const handleMultipleAnswerToggle = (label: QuestionOptionLabel) => {
    const nextAnswers = questionForm.multipleAnswers.includes(label)
      ? questionForm.multipleAnswers.filter((item) => item !== label)
      : [...questionForm.multipleAnswers, label]

    onQuestionFormChange({
      ...questionForm,
      multipleAnswers: QUESTION_OPTION_LABELS.filter((item) => nextAnswers.includes(item)),
    })
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 backdrop-blur-[2px] sm:p-5"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
          className="relative flex h-[88vh] w-[94vw] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_40px_80px_-30px_rgba(15,23,42,0.65)] lg:h-auto"
          style={{
            width: 'min(1180px, 92vw)',
            height: 'min(82vh, 900px)',
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <div className={`h-1.5 shrink-0 bg-gradient-to-r ${nodeAccentClass}`} />

          <header className="shrink-0 border-b border-slate-200 bg-gradient-to-b from-white to-slate-50 px-4 py-3 sm:px-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-flex h-6 items-center rounded-full border px-2.5 text-[11px] font-semibold ${nodeTypeTagClass}`}
                  >
                    {nodeTypeLabel}
                  </span>
                  {selectedNode.is_orphan && selectedNode.node_type === 'question' && (
                    <span className="inline-flex h-6 items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 text-[11px] font-semibold text-amber-700">
                      待关联
                    </span>
                  )}
                </div>
                <h3 className="line-clamp-2 text-lg font-semibold leading-7 text-slate-900">{selectedNode.label}</h3>
              </div>
              <button
                onClick={onClose}
                className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition-all hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800"
                aria-label="关闭详情"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </header>

          <section className="shrink-0 border-b border-slate-200 bg-slate-50/80 px-4 py-2.5 sm:px-5">
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5">
                <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500">连接数</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{selectedNodeConnections}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5">
                <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500">权重</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{selectedNode.weight}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5">
                <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500">节点类型</p>
                <p className="mt-1 truncate text-sm font-semibold text-slate-900">{nodeTypeLabel}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5">
                <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500">节点 ID</p>
                <p className="mt-1 truncate text-xs font-semibold text-slate-700">{selectedNode.id}</p>
              </div>
            </div>
          </section>

          <section className="min-h-0 flex-1 overflow-auto bg-slate-50/70 px-4 py-3 sm:px-5">
            {detailLoading && (
              <div className="inline-flex items-center gap-2 text-sm text-slate-600">
                <Loader2 className="h-4 w-4 animate-spin" /> 加载中...
              </div>
            )}
            {detailError && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {detailError}
              </div>
            )}

            {!detailLoading && !detailError && selectedNode.node_type === 'knowledge_point' && knowledgePointDetail && (
              <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-800">关联片段（Chunks）</div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={onOpenDocumentPreview}
                        disabled={documentLoading || deletingKnowledgePoint}
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 hover:border-indigo-200 hover:text-indigo-600 disabled:opacity-60"
                      >
                        {documentLoading ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Eye className="h-3.5 w-3.5" />
                        )}{' '}
                        原文
                      </button>
                      <button
                        onClick={onDeleteKnowledgePoint}
                        disabled={deletingKnowledgePoint}
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-2.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        {deletingKnowledgePoint ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}{' '}
                        删除
                      </button>
                    </div>
                  </div>

                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      value={chunkSearch}
                      onChange={(event) => onChunkSearchChange(event.target.value)}
                      placeholder="筛选 Chunk 内容"
                      className="h-9 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                    />
                  </div>

                  <div className="space-y-2">
                    {visibleChunks.length > 0 ? (
                      visibleChunks.map((chunk) => (
                        <div key={chunk.id} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                          <p className="mb-1 text-[11px] font-semibold tracking-[0.06em] text-indigo-600">
                            CHUNK #{chunk.chunk_index}
                          </p>
                          <p className="whitespace-pre-wrap text-xs leading-6 text-slate-700">{chunk.content}</p>
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-slate-500">未找到匹配内容</div>
                    )}
                  </div>

                  {filteredChunks.length > 3 && (
                    <button
                      onClick={onToggleShowAllChunks}
                      className="text-xs font-semibold text-indigo-600 transition-all hover:text-indigo-700"
                    >
                      {showAllChunks ? '收起部分 chunk' : `展开全部 ${filteredChunks.length} 个 chunk`}
                    </button>
                  )}
                </div>

                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="text-sm font-semibold text-slate-800">节点元信息</div>
                  <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                    <p>
                      <span className="font-medium text-slate-900">ID：</span>
                      {knowledgePointDetail.id}
                    </p>
                    <p>
                      <span className="font-medium text-slate-900">Chunk 数：</span>
                      {knowledgePointDetail.chunks.length}
                    </p>
                    <p>
                      <span className="font-medium text-slate-900">连接数：</span>
                      {selectedNodeConnections}
                    </p>
                    <p>
                      <span className="font-medium text-slate-900">权重：</span>
                      {selectedNode.weight}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {!detailLoading && !detailError && selectedNode.node_type === 'question' && (
              <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="text-sm font-semibold text-slate-800">题干与概览</div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800">
                    <p className="whitespace-pre-wrap leading-6">{questionForm.questionText || '未设置题干'}</p>
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                      <p className="text-xs text-slate-500">题型</p>
                      <p className="mt-1 font-medium text-slate-900">
                        {questionTypeOptions.find((item) => item.value === questionForm.questionType)?.label ??
                          questionForm.questionType}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                      <p className="text-xs text-slate-500">答案</p>
                      <p className="mt-1 font-medium text-slate-900">{getAnswerPreview(questionForm)}</p>
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                    <p className="text-xs text-slate-500">当前已关联知识点</p>
                    <p className="mt-1 leading-6 text-slate-900">
                      {linkedKnowledgeTitle.length > 0 ? linkedKnowledgeTitle.join('、') : '暂无关联知识点'}
                    </p>
                  </div>
                </div>

                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-800">题目编辑</div>
                    <button
                      onClick={onToggleQuestionEdit}
                      className="text-xs font-semibold text-indigo-600 transition-all hover:text-indigo-700"
                    >
                      {questionEditMode ? '收起编辑' : '编辑题目'}
                    </button>
                  </div>

                  {questionEditMode ? (
                    <div className="space-y-4">
                      <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs leading-5 text-indigo-700">
                        该编辑入口与题库管理页使用同一题型规则：单/多选仅支持 A/B/C/D，判断题保存为 true/false，简答题直接保存文本答案。
                      </div>

                      <textarea
                        value={questionForm.questionText}
                        onChange={(event) =>
                          onQuestionFormChange({
                            ...questionForm,
                            questionText: event.target.value,
                          })
                        }
                        rows={4}
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                      />

                      <select
                        value={questionForm.questionType}
                        onChange={(event) =>
                          onQuestionFormChange(changeEditorType(questionForm, event.target.value as QuestionType))
                        }
                        className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                      >
                        {questionTypeOptions.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>

                      {(questionForm.questionType === 'single' || questionForm.questionType === 'multiple') && (
                        <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                          <div>
                            <h4 className="text-sm font-semibold text-slate-800">选项与答案</h4>
                            <p className="mt-1 text-xs text-slate-500">A/B 必填，C/D 选填，不能跳空。</p>
                          </div>
                          {QUESTION_OPTION_LABELS.map((label) => (
                            <div
                              key={label}
                              className="grid grid-cols-[auto,1fr] gap-3 md:grid-cols-[auto,1fr,auto] md:items-center"
                            >
                              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white">
                                {label}
                              </div>
                              <input
                                value={questionForm.optionTexts[label]}
                                onChange={(event) => handleOptionTextChange(label, event.target.value)}
                                placeholder={`请输入 ${label} 选项内容`}
                                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700"
                              />
                              {questionForm.questionType === 'single' ? (
                                <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                                  <input
                                    type="radio"
                                    name="knowledge-graph-single-answer"
                                    checked={questionForm.singleAnswer === label}
                                    onChange={() =>
                                      onQuestionFormChange({
                                        ...questionForm,
                                        singleAnswer: label,
                                      })
                                    }
                                  />
                                  设为答案
                                </label>
                              ) : (
                                <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                                  <input
                                    type="checkbox"
                                    checked={questionForm.multipleAnswers.includes(label)}
                                    onChange={() => handleMultipleAnswerToggle(label)}
                                  />
                                  设为答案
                                </label>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {questionForm.questionType === 'true_false' && (
                        <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                          <h4 className="text-sm font-semibold text-slate-800">判断题答案</h4>
                          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            {[
                              { value: 'true', label: '对' },
                              { value: 'false', label: '错' },
                            ].map((option) => (
                              <button
                                key={option.value}
                                type="button"
                                onClick={() =>
                                  onQuestionFormChange({
                                    ...questionForm,
                                    trueFalseAnswer: option.value as 'true' | 'false',
                                  })
                                }
                                className={`rounded-2xl border px-4 py-4 text-left text-sm transition-all ${
                                  questionForm.trueFalseAnswer === option.value
                                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700 shadow-sm'
                                    : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200'
                                }`}
                              >
                                <span className="font-semibold">{option.label}</span>
                                <p className="mt-1 text-xs text-slate-500">提交时将保存为 {option.value}</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {questionForm.questionType === 'short_answer' && (
                        <textarea
                          value={questionForm.shortAnswer}
                          onChange={(event) =>
                            onQuestionFormChange({
                              ...questionForm,
                              shortAnswer: event.target.value,
                            })
                          }
                          rows={4}
                          placeholder="请输入简答题答案"
                          className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                        />
                      )}

                      <textarea
                        value={questionForm.explanation}
                        onChange={(event) =>
                          onQuestionFormChange({
                            ...questionForm,
                            explanation: event.target.value,
                          })
                        }
                        rows={3}
                        placeholder="解析"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                      />

                      <div className="space-y-2">
                        <input
                          type="text"
                          value={knowledgeSearch}
                          onChange={(event) => onKnowledgeSearchChange(event.target.value)}
                          placeholder="搜索知识点"
                          className="h-9 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-100"
                        />
                        <div className="max-h-[180px] space-y-1 overflow-auto rounded-xl border border-slate-200 bg-white p-2">
                          {knowledgePointCandidates.map((item) => {
                            const checked = selectedKnowledgeIds.has(item.id)
                            return (
                              <label
                                key={item.id}
                                className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
                                  checked ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-slate-50'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(event) =>
                                    onToggleKnowledgeSelection(item.id, event.target.checked)
                                  }
                                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <span className="truncate">{item.title}</span>
                              </label>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                      点击“编辑题目”后可修改题干、按题型编辑答案，并维护知识点映射。
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          <footer className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-white px-5 py-3 sm:px-6">
            <p className="text-xs text-slate-500">支持 ESC、遮罩点击、右上角按钮关闭</p>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="inline-flex h-9 items-center rounded-xl border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:border-slate-300 hover:text-slate-700"
              >
                关闭
              </button>
              {selectedNode.node_type === 'question' && questionEditMode && (
                <button
                  onClick={onSaveQuestion}
                  disabled={questionSaving}
                  className="inline-flex h-9 items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 px-3 text-xs font-semibold text-white shadow-lg shadow-indigo-500/25 hover:from-indigo-600 hover:to-violet-700 disabled:opacity-60"
                >
                  {questionSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}{' '}
                  保存变更
                </button>
              )}
            </div>
          </footer>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

import { useEffect } from 'react'
import { X } from 'lucide-react'

import type { KnowledgePointResponse, QuestionType } from '../../types'
import {
  changeEditorType,
  QUESTION_OPTION_LABELS,
  type QuestionEditorFormState,
  type QuestionOptionLabel,
} from './questionEditorUtils'

interface QuestionEditorModalProps {
  title: string
  open: boolean
  saving: boolean
  state: QuestionEditorFormState
  onChange: (state: QuestionEditorFormState) => void
  onClose: () => void
  onSubmit: () => void
  submitLabel: string
  knowledgeSearch: string
  onKnowledgeSearchChange: (value: string) => void
  knowledgeLoading: boolean
  knowledgeCandidates: KnowledgePointResponse[]
  selectedKnowledgeIds: Set<string>
  onToggleKnowledgeId: (id: string) => void
}

const questionTypeOptions: Array<{ value: QuestionType; label: string }> = [
  { value: 'single', label: '单选题' },
  { value: 'multiple', label: '多选题' },
  { value: 'true_false', label: '判断题' },
  { value: 'short_answer', label: '简答题' },
]

export default function QuestionEditorModal({
  title,
  open,
  saving,
  state,
  onChange,
  onClose,
  onSubmit,
  submitLabel,
  knowledgeSearch,
  onKnowledgeSearchChange,
  knowledgeLoading,
  knowledgeCandidates,
  selectedKnowledgeIds,
  onToggleKnowledgeId,
}: QuestionEditorModalProps) {
  useEffect(() => {
    if (!open) return

    const body = document.body
    const root = document.documentElement
    const lockCount = Number(body.dataset.modalScrollLockCount ?? '0')

    if (lockCount === 0) {
      body.dataset.prevOverflow = body.style.overflow
      body.dataset.prevOverscrollBehavior = body.style.overscrollBehavior
      root.dataset.prevOverflow = root.style.overflow

      body.style.overflow = 'hidden'
      body.style.overscrollBehavior = 'none'
      root.style.overflow = 'hidden'
    }

    body.dataset.modalScrollLockCount = String(lockCount + 1)

    return () => {
      const nextLockCount = Math.max(0, Number(body.dataset.modalScrollLockCount ?? '1') - 1)

      if (nextLockCount === 0) {
        body.style.overflow = body.dataset.prevOverflow ?? ''
        body.style.overscrollBehavior = body.dataset.prevOverscrollBehavior ?? ''
        root.style.overflow = root.dataset.prevOverflow ?? ''

        delete body.dataset.modalScrollLockCount
        delete body.dataset.prevOverflow
        delete body.dataset.prevOverscrollBehavior
        delete root.dataset.prevOverflow
        return
      }

      body.dataset.modalScrollLockCount = String(nextLockCount)
    }
  }, [open])

  if (!open) return null

  const handleOptionTextChange = (label: QuestionOptionLabel, value: string) => {
    const nextState: QuestionEditorFormState = {
      ...state,
      optionTexts: {
        ...state.optionTexts,
        [label]: value,
      },
    }

    if (!value.trim()) {
      if (state.singleAnswer === label) {
        nextState.singleAnswer = ''
      }
      if (state.multipleAnswers.includes(label)) {
        nextState.multipleAnswers = state.multipleAnswers.filter((item) => item !== label)
      }
    }

    onChange(nextState)
  }

  const handleTypeChange = (value: QuestionType) => {
    onChange(changeEditorType(state, value))
  }

  const handleMultipleAnswerToggle = (label: QuestionOptionLabel) => {
    const nextAnswers = state.multipleAnswers.includes(label)
      ? state.multipleAnswers.filter((item) => item !== label)
      : [...state.multipleAnswers, label]
    onChange({
      ...state,
      multipleAnswers: QUESTION_OPTION_LABELS.filter((item) => nextAnswers.includes(item)),
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-slate-950/50 px-4 py-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="flex max-h-[calc(100dvh-3rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
            <p className="mt-1 text-xs text-slate-500">按题型填写统一规则：单/多选仅支持 A/B/C/D；判断题入库为 true/false。</p>
          </div>
          <button type="button" onClick={onClose}>
            <X className="h-4 w-4 text-slate-500" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          <div className="grid gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">题干</label>
              <textarea
                value={state.questionText}
                onChange={(e) => onChange({ ...state, questionText: e.target.value })}
                placeholder="请输入题干"
                rows={3}
                className="w-full rounded-xl border border-slate-200 p-3 text-sm"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">题型</span>
                <select
                  value={state.questionType}
                  onChange={(e) => handleTypeChange(e.target.value as QuestionType)}
                  className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-600"
                >
                  {questionTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-xs leading-5 text-indigo-700">
                {state.questionType === 'single' && '答案必须从已填写的 A/B/C/D 中选择 1 个。'}
                {state.questionType === 'multiple' && '答案必须从已填写的 A/B/C/D 中选择至少 2 个，提交为 A,C 这种格式。'}
                {state.questionType === 'true_false' && '判断题前端显示对/错，后端统一保存为 true / false。'}
                {state.questionType === 'short_answer' && '简答题不允许选项，答案直接填写文本。'}
              </div>
            </div>

            {(state.questionType === 'single' || state.questionType === 'multiple') && (
              <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-800">选项与答案</h4>
                    <p className="mt-1 text-xs text-slate-500">A/B 必填，C/D 选填；必须连续填写，不能跳空。</p>
                  </div>
                </div>
                <div className="space-y-3">
                  {QUESTION_OPTION_LABELS.map((label) => (
                    <div key={label} className="grid grid-cols-[auto,1fr] gap-3 md:grid-cols-[auto,1fr,auto] md:items-center">
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white">
                        {label}
                      </div>
                      <input
                        value={state.optionTexts[label]}
                        onChange={(e) => handleOptionTextChange(label, e.target.value)}
                        placeholder={`请输入 ${label} 选项内容`}
                        className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700"
                      />
                      {state.questionType === 'single' ? (
                        <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                          <input
                            type="radio"
                            name={`${title}-single-answer`}
                            checked={state.singleAnswer === label}
                            onChange={() => onChange({ ...state, singleAnswer: label })}
                          />
                          设为答案
                        </label>
                      ) : (
                        <label className="inline-flex items-center gap-2 text-sm text-slate-600">
                          <input
                            type="checkbox"
                            checked={state.multipleAnswers.includes(label)}
                            onChange={() => handleMultipleAnswerToggle(label)}
                          />
                          设为答案
                        </label>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {state.questionType === 'true_false' && (
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
                      onClick={() => onChange({ ...state, trueFalseAnswer: option.value as 'true' | 'false' })}
                      className={`rounded-2xl border px-4 py-4 text-left text-sm transition-all ${
                        state.trueFalseAnswer === option.value
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

            {state.questionType === 'short_answer' && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700">标准答案</label>
                <textarea
                  value={state.shortAnswer}
                  onChange={(e) => onChange({ ...state, shortAnswer: e.target.value })}
                  placeholder="请输入简答题答案"
                  rows={4}
                  className="w-full rounded-xl border border-slate-200 p-3 text-sm"
                />
              </div>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">解析（可选）</label>
              <textarea
                value={state.explanation}
                onChange={(e) => onChange({ ...state, explanation: e.target.value })}
                placeholder="请输入题目解析"
                rows={3}
                className="w-full rounded-xl border border-slate-200 p-3 text-sm"
              />
            </div>

            <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
              <div>
                <h4 className="text-sm font-semibold text-slate-800">知识点绑定</h4>
                <p className="mt-1 text-xs text-slate-500">支持继续绑定知识点，本轮不改动该业务流程。</p>
              </div>
              <input
                value={knowledgeSearch}
                onChange={(e) => onKnowledgeSearchChange(e.target.value)}
                placeholder="搜索知识点"
                className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
              />
              <div className="max-h-56 overflow-y-auto overscroll-contain rounded-xl border border-slate-200 p-2">
                {knowledgeLoading ? (
                  <div className="p-4 text-center text-sm text-slate-500">加载中...</div>
                ) : knowledgeCandidates.length === 0 ? (
                  <div className="p-4 text-center text-sm text-slate-500">暂无知识点</div>
                ) : (
                  knowledgeCandidates.map((item) => {
                    const checked = selectedKnowledgeIds.has(item.id)
                    return (
                      <label key={item.id} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 hover:bg-slate-50">
                        <input type="checkbox" checked={checked} onChange={() => onToggleKnowledgeId(item.id)} />
                        <span className="text-sm text-slate-700">{item.title}</span>
                      </label>
                    )
                  })
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button type="button" className="rounded-lg border border-slate-200 px-3 py-2 text-sm" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            {saving ? '保存中...' : submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

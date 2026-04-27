import { useCallback, useMemo, useState } from 'react'

import type { QuestionBankResponse, QuestionResponse } from '../types'

interface UseQuestionManagementFiltersArgs {
  questions: QuestionResponse[]
  total: number
  page: number
  pageSize: number
  questionBanks: QuestionBankResponse[]
  fetchQuestions: (params?: {
    page?: number
    pageSize?: number
    q?: string
    bankId?: string
    questionType?: string
    isDirty?: boolean
  }) => Promise<void>
}

export function useQuestionManagementFilters({
  questions,
  total,
  page,
  pageSize,
  questionBanks,
  fetchQuestions,
}: UseQuestionManagementFiltersArgs) {
  const [searchTerm, setSearchTerm] = useState('')
  const [questionType, setQuestionType] = useState('all')
  const [dirtyFilter, setDirtyFilter] = useState<'all' | 'dirty' | 'clean'>('all')
  const [selectedBankId, setSelectedBankId] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const allSelected = questions.length > 0 && questions.every((item) => selectedIds.has(item.id))
  const selectedBank = useMemo(
    () => questionBanks.find((bank) => bank.id === selectedBankId) || null,
    [questionBanks, selectedBankId]
  )

  const runSearch = useCallback(
    async (targetPage = 1) => {
      await fetchQuestions({
        page: targetPage,
        pageSize,
        q: searchTerm.trim(),
        bankId: selectedBankId,
        questionType,
        isDirty: dirtyFilter === 'all' ? undefined : dirtyFilter === 'dirty',
      })
    },
    [dirtyFilter, fetchQuestions, pageSize, questionType, searchTerm, selectedBankId]
  )

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (allSelected) return new Set()
      const next = new Set(prev)
      questions.forEach((item) => next.add(item.id))
      return next
    })
  }, [allSelected, questions])

  return {
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
    page,
    pageSize,
  }
}

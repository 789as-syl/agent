import { useState, type ChangeEvent, type Dispatch, type SetStateAction } from 'react'
import { toast } from 'sonner'

import {
  createQuestionBank,
  deleteQuestion as deleteQuestionRequest,
  deleteQuestionBank,
  updateQuestionBank,
} from '../api/admin-questions'
import { extractApiErrorMessage } from '../api'
import type { QuestionBankResponse, QuestionImportResponse, VectorizationJobResponse } from '../types'

interface UseQuestionManagementActionsArgs {
  deleteQuestion: (id: string) => Promise<void>
  importQuestions: (data: FormData) => Promise<QuestionImportResponse>
  vectorizeQuestions: (data?: { only_dirty?: boolean; batch_size?: number }) => Promise<VectorizationJobResponse>
  pollVectorizationJob: (jobId: string) => Promise<void>
  fetchQuestionBanks: () => Promise<void>
  runSearch: (targetPage?: number) => Promise<void>
  setSelectedBankId: Dispatch<SetStateAction<string>>
  setSelectedIds: Dispatch<SetStateAction<Set<string>>>
  selectedIds: Set<string>
  selectedBankId: string
  selectedBank: QuestionBankResponse | null
  page: number
}

const formatImportSummary = (result: QuestionImportResponse) =>
  `\u5bfc\u5165\u5b8c\u6210\uff1a\u65b0\u589e ${result.created}\uff0c\u66f4\u65b0 ${result.updated}\uff0c\u8df3\u8fc7 ${result.skipped}\uff0c\u5931\u8d25 ${result.failed}`

export function useQuestionManagementActions({
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
}: UseQuestionManagementActionsArgs) {
  const [isVectorizing, setIsVectorizing] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [createBankOpen, setCreateBankOpen] = useState(false)
  const [editBankOpen, setEditBankOpen] = useState(false)
  const [bankSaving, setBankSaving] = useState(false)
  const [bankName, setBankName] = useState('')
  const [bankDescription, setBankDescription] = useState('')

  const closeBankModal = () => {
    setCreateBankOpen(false)
    setEditBankOpen(false)
  }

  const resetBankForm = () => {
    setBankName('')
    setBankDescription('')
  }

  const handleDelete = async (questionId: string) => {
    if (!window.confirm('\u786e\u5b9a\u8981\u5220\u9664\u8fd9\u9053\u9898\u76ee\u5417\uff1f')) {
      return
    }

    try {
      await deleteQuestion(questionId)
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.delete(questionId)
        return next
      })
      toast.success('\u9898\u76ee\u5df2\u5220\u9664')
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '\u9898\u76ee\u5220\u9664\u5931\u8d25'))
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) {
      toast.error('\u8bf7\u5148\u9009\u62e9\u9898\u76ee')
      return
    }

    if (!window.confirm(`\u786e\u5b9a\u5220\u9664\u9009\u4e2d\u7684 ${selectedIds.size} \u9053\u9898\u76ee\u5417\uff1f`)) {
      return
    }

    const ids = [...selectedIds]
    const results = await Promise.allSettled(ids.map((id) => deleteQuestionRequest(id)))
    const failedCount = results.filter((item) => item.status === 'rejected').length

    if (failedCount > 0) {
      toast.error(
        `\u6279\u91cf\u5220\u9664\u90e8\u5206\u5931\u8d25\uff1a\u6210\u529f ${ids.length - failedCount}\uff0c\u5931\u8d25 ${failedCount}`
      )
    } else {
      toast.success('\u6279\u91cf\u5220\u9664\u6210\u529f')
    }

    setSelectedIds(new Set<string>())
    await runSearch(page)
  }

  const handleVectorize = async () => {
    setIsVectorizing(true)
    try {
      const job = await vectorizeQuestions({ only_dirty: true, batch_size: 10 })
      toast.success(`\u5411\u91cf\u5316\u4efb\u52a1\u5df2\u89e6\u53d1\uff1a${job.id}`)
      await pollVectorizationJob(job.id)
      toast.success('\u5411\u91cf\u5316\u5b8c\u6210')
      await runSearch(page)
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '\u5411\u91cf\u5316\u5931\u8d25'))
    } finally {
      setIsVectorizing(false)
    }
  }

  const handleFileImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.target
    const file = input.files?.[0]
    if (!file) {
      return
    }

    if (!selectedBankId) {
      toast.error('\u8bf7\u5148\u9009\u62e9\u9898\u5e93')
      input.value = ''
      return
    }

    setIsImporting(true)
    try {
      const formData = new FormData()
      formData.append('bank_id', selectedBankId)
      formData.append('file', file)

      const result = await importQuestions(formData)
      toast.success(formatImportSummary(result))

      if (result.failed > 0 || result.errors.length > 0) {
        toast.error('\u5b58\u5728\u5931\u8d25\u884c\uff0c\u8bf7\u68c0\u67e5\u5bfc\u5165\u6587\u4ef6\u5185\u5bb9')
        if (result.errors.length > 0) {
          toast.error(result.errors.slice(0, 2).join('\uff1b'))
        }
        if (result.errors.length > 2) {
          toast.error('\u66f4\u591a\u9519\u8bef\u8bf7\u5206\u6279\u6392\u67e5')
        }
      }

      await runSearch(1)
    } catch (error) {
      toast.error(
        extractApiErrorMessage(error, '\u5bfc\u5165\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6587\u4ef6\u683c\u5f0f\u4e0e\u9898\u578b\u5b57\u6bb5')
      )
    } finally {
      setIsImporting(false)
      input.value = ''
    }
  }

  const openCreateBank = () => {
    resetBankForm()
    setEditBankOpen(false)
    setCreateBankOpen(true)
  }

  const openEditBank = (bank: QuestionBankResponse) => {
    setBankName(bank.name)
    setBankDescription(bank.description ?? '')
    setCreateBankOpen(false)
    setEditBankOpen(true)
  }

  const handleCreateBank = async () => {
    const name = bankName.trim()
    if (!name) {
      toast.error('\u9898\u5e93\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a')
      return
    }

    setBankSaving(true)
    try {
      await createQuestionBank({
        name,
        description: bankDescription.trim() || undefined,
      })
      await fetchQuestionBanks()
      closeBankModal()
      resetBankForm()
      toast.success('\u9898\u5e93\u521b\u5efa\u6210\u529f')
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '\u9898\u5e93\u521b\u5efa\u5931\u8d25'))
    } finally {
      setBankSaving(false)
    }
  }

  const handleUpdateBank = async () => {
    if (!selectedBank) {
      toast.error('\u8bf7\u5148\u9009\u62e9\u9898\u5e93')
      return
    }

    const name = bankName.trim()
    if (!name) {
      toast.error('\u9898\u5e93\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a')
      return
    }

    setBankSaving(true)
    try {
      await updateQuestionBank(selectedBank.id, {
        name,
        description: bankDescription.trim() || undefined,
      })
      await fetchQuestionBanks()
      closeBankModal()
      toast.success('\u9898\u5e93\u66f4\u65b0\u6210\u529f')
    } catch (error) {
      toast.error(extractApiErrorMessage(error, '\u9898\u5e93\u66f4\u65b0\u5931\u8d25'))
    } finally {
      setBankSaving(false)
    }
  }

  const handleDeleteBank = async () => {
    if (!selectedBank) {
      toast.error('\u8bf7\u5148\u9009\u62e9\u9898\u5e93')
      return
    }

    if (!window.confirm(`\u786e\u5b9a\u5220\u9664\u9898\u5e93\u201c${selectedBank.name}\u201d\u5417\uff1f`)) {
      return
    }

    try {
      await deleteQuestionBank(selectedBank.id)
      await fetchQuestionBanks()
      setSelectedIds(new Set<string>())
      await runSearch(1)
      setSelectedBankId('')
      toast.success('\u9898\u5e93\u5220\u9664\u6210\u529f')
    } catch (error) {
      toast.error(
        extractApiErrorMessage(error, '\u9898\u5e93\u5220\u9664\u5931\u8d25\uff08\u9898\u5e93\u5185\u53ef\u80fd\u4ecd\u6709\u9898\u76ee\uff09')
      )
    }
  }

  return {
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
  }
}

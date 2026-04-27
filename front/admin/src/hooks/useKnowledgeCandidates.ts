import { useCallback, useState } from 'react'

import * as adminIngestionApi from '../api/admin-ingestion'
import { extractApiErrorMessage } from '../api'
import type { KnowledgePointResponse } from '../types'

interface UseKnowledgeCandidatesOptions {
  onError?: (message: string) => void
}

export function useKnowledgeCandidates(options: UseKnowledgeCandidatesOptions = {}) {
  const { onError } = options
  const [knowledgeCandidates, setKnowledgeCandidates] = useState<KnowledgePointResponse[]>([])
  const [knowledgeLoading, setKnowledgeLoading] = useState(false)

  const loadKnowledgeCandidates = useCallback(async () => {
    setKnowledgeLoading(true)
    try {
      const response = await adminIngestionApi.getKnowledgePoints({
        page: 1,
        page_size: 200,
        include_chunks: false,
      })
      setKnowledgeCandidates(response.items)
    } catch (error) {
      onError?.(extractApiErrorMessage(error, '加载知识点失败'))
    } finally {
      setKnowledgeLoading(false)
    }
  }, [onError])

  return {
    knowledgeCandidates,
    knowledgeLoading,
    loadKnowledgeCandidates,
  }
}

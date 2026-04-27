import { useCallback } from 'react'
import axios from 'axios'

import type { VectorizationJobResponse } from '../types'

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

export function useVectorizationJobPolling(
  getVectorizationJob: (jobId: string) => Promise<VectorizationJobResponse>
) {
  return useCallback(
    async (jobId: string) => {
      let waitMs = 1200

      for (let i = 0; i < 120; i += 1) {
        let job: VectorizationJobResponse

        try {
          job = await getVectorizationJob(jobId)
        } catch (error) {
          if (axios.isAxiosError(error) && error.response?.status === 429) {
            await sleep(waitMs)
            waitMs = Math.min(5000, waitMs + 500)
            continue
          }
          throw error
        }

        if (job.status === 'success') {
          return
        }

        if (job.status === 'failed') {
          throw new Error(job.error_message || '\u5411\u91cf\u5316\u5931\u8d25')
        }

        await sleep(waitMs)
        waitMs = Math.min(3000, waitMs + 100)
      }

      throw new Error('\u5411\u91cf\u5316\u8d85\u65f6')
    },
    [getVectorizationJob]
  )
}

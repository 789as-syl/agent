export interface RagGoldenQueryCreate {
  name: string
  query: string
  expected_answer?: string | null
  expected_source_ids: string[]
  tags: string[]
}

export interface RagGoldenQueryResponse {
  id: string
  name: string
  query: string
  expected_answer?: string | null
  expected_source_ids: string[]
  tags: string[]
  is_active: boolean
  created_by_user_id: string
  created_at: string
  updated_at: string
}

export interface RagGoldenQueryListResponse {
  items: RagGoldenQueryResponse[]
  total: number
  page: number
  page_size: number
}

export interface RagEvalRunCreate {
  golden_query_id?: string | null
  query?: string | null
}

export interface RagEvalRunResponse {
  id: string
  golden_query_id?: string | null
  query: string
  status: string
  score: number
  evidence_count: number
  missing_expected_count: number
  result_json: Record<string, unknown>
  error_message?: string | null
  created_by_user_id: string
  created_at: string
  updated_at: string
}

export interface RagEvalRunListResponse {
  items: RagEvalRunResponse[]
  total: number
  page: number
  page_size: number
}

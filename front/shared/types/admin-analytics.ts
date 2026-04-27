export type AdminRange = '1d' | '7d' | '30d'

export interface DashboardMetrics {
  request_count: number
  hit_rate: number
  avg_latency_ms: number
  document_count: number
}

export interface DashboardTrendPoint {
  bucket: string
  request_count: number
  hit_count: number
  avg_latency_ms: number
}

export interface DashboardBreakdownItem {
  key: string
  label: string
  value: number
}

export interface KnowledgeHeatItem {
  knowledge_point_id: string
  title: string
  count: number
}

export interface AdminDashboardResponse {
  range: AdminRange
  metrics: DashboardMetrics
  trends: DashboardTrendPoint[]
  result_breakdown: DashboardBreakdownItem[]
  knowledge_heat: KnowledgeHeatItem[]
}

export interface GraphNode {
  id: string
  label: string
  node_type: 'knowledge_point' | 'question'
  weight: number
  is_orphan?: boolean
  link_count?: number
}

export interface GraphLink {
  source: string
  target: string
  weight: number
}

export interface KnowledgeGraphSummary {
  node_count: number
  edge_count: number
  knowledge_point_count: number
  question_count: number
}

export interface KnowledgeGraphResponse {
  range: AdminRange
  nodes: GraphNode[]
  links: GraphLink[]
  summary: KnowledgeGraphSummary
}

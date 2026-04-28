import { BookOpenText } from 'lucide-react'

import type { ExecutionTraceEntry } from '../../../types'
import type { ProductTraceEvidenceItem } from '../message-utils'

function getEvidenceTitle(item: ProductTraceEvidenceItem): string {
  return item.title || item.label || item.source || '证据'
}

function getEvidenceSnippet(item: ProductTraceEvidenceItem): string | undefined {
  return item.snippet || item.detail
}

function getEvidenceSourceLabel(item: ProductTraceEvidenceItem): string {
  return item.source_type || item.source || item.evidence_type || '来源'
}

function buildEvidenceItems(trace: ExecutionTraceEntry[] | null | undefined): ProductTraceEvidenceItem[] {
  if (!Array.isArray(trace)) return []
  const seen = new Set<string>()
  const items: ProductTraceEvidenceItem[] = []

  trace.forEach((entry) => {
    entry.evidence?.forEach((evidence) => {
      const item = evidence as ProductTraceEvidenceItem
      const key = [
        item.source,
        getEvidenceTitle(item),
        getEvidenceSnippet(item) || '',
        item.locator || '',
      ].join('::')
      if (seen.has(key)) return
      seen.add(key)
      items.push(item)
    })
  })

  return items
}

export default function AssistantEvidencePanel({ trace }: { trace: ExecutionTraceEntry[] | null | undefined }) {
  const evidenceItems = buildEvidenceItems(trace)
  if (evidenceItems.length === 0) return null

  return (
    <section className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-600">
        <BookOpenText className="h-4 w-4 text-indigo-500" />
        证据卡片 ({evidenceItems.length})
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {evidenceItems.map((item, index) => (
          <div key={`${item.source}-${getEvidenceTitle(item)}-${index}`} className="rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="line-clamp-2 text-sm font-medium text-slate-800">{getEvidenceTitle(item)}</p>
                {(item.locator || item.evidence_type) && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.locator && (
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-600">
                        {item.locator}
                      </span>
                    )}
                    {item.evidence_type && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                        {item.evidence_type}
                      </span>
                    )}
                  </div>
                )}
              </div>
              <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                {getEvidenceSourceLabel(item)}
              </span>
            </div>
            {getEvidenceSnippet(item) && (
              <p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-600">{getEvidenceSnippet(item)}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

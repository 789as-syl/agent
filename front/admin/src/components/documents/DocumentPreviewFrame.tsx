import type { KnowledgePointPreviewState } from '../../api/admin-ingestion'

interface DocumentPreviewFrameProps {
  previewUrl: string
  previewState: KnowledgePointPreviewState | null
  previewStateMessage: string
  emptyMessage?: string
  className?: string
}

export default function DocumentPreviewFrame({
  previewUrl,
  previewState,
  previewStateMessage,
  emptyMessage = '预览地址为空',
  className = 'min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-200 bg-white',
}: DocumentPreviewFrameProps) {
  return (
    <>
      {previewState && previewState !== 'ready' && (
        <div
          className={`mb-3 rounded-lg border px-3 py-2 text-xs ${
            previewState === 'failed'
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : 'border-amber-200 bg-amber-50 text-amber-700'
          }`}
        >
          {previewStateMessage}
        </div>
      )}

      <div className={className}>
        {previewUrl ? (
          <iframe title="document-preview" src={previewUrl} className="h-full w-full border-0" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">{emptyMessage}</div>
        )}
      </div>
    </>
  )
}

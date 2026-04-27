import { RotateCcw, Send, StopCircle } from 'lucide-react'

interface ChatComposerProps {
  input: string
  isRunning: boolean
  hasMessages: boolean
  retryTitle?: string
  statusText?: string
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  onInputChange: (value: string) => void
  onSend: () => Promise<void>
  onRetry: () => Promise<void>
  onInterrupt: () => Promise<void>
}

export default function ChatComposer({
  input,
  isRunning,
  hasMessages,
  retryTitle = '继续 / 重试 / 重新生成',
  statusText,
  textareaRef,
  onInputChange,
  onSend,
  onRetry,
  onInterrupt,
}: ChatComposerProps) {
  return (
    <div className="border-t border-slate-200/80 bg-white/90 p-4 backdrop-blur lg:px-6">
      <div className="mx-auto w-full max-w-4xl">
        <div className="relative rounded-2xl border border-slate-200 bg-white p-2 shadow-lg shadow-slate-900/5">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void onSend()
              }
            }}
            placeholder="输入你的问题，例如：帮我总结这份文档的关键结论"
            disabled={isRunning}
            rows={1}
            className="max-h-[200px] min-h-[44px] w-full resize-none rounded-xl px-3 py-2 pr-24 text-[15px] leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-70"
          />

          <div className="absolute bottom-2 right-2 flex items-center gap-2">
            {!isRunning ? (
              <>
                {hasMessages && (
                  <button
                    onClick={() => void onRetry()}
                    className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
                    title={retryTitle}
                  >
                    <RotateCcw className="h-[18px] w-[18px]" />
                  </button>
                )}
                <button
                  onClick={() => void onSend()}
                  disabled={!input.trim()}
                  className="rounded-lg bg-indigo-600 p-2 text-white transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
                  title="发送"
                >
                  <Send className="h-[18px] w-[18px]" />
                </button>
              </>
            ) : (
              <button
                onClick={() => void onInterrupt()}
                className="rounded-lg bg-red-500 p-2 text-white transition-all hover:bg-red-600"
                title="中断"
              >
                <StopCircle className="h-[18px] w-[18px]" />
              </button>
            )}
          </div>
        </div>

        <div className="mt-2 flex items-center justify-between px-1 text-xs text-slate-400">
          <span>Enter 发送，Shift + Enter 换行</span>
          <span>{statusText || (isRunning ? '模型正在生成回答...' : '支持 Markdown、表格与代码块')}</span>
        </div>
      </div>
    </div>
  )
}

import { motion } from 'framer-motion'
import { Sparkles } from 'lucide-react'

interface ChatEmptyStateProps {
  prompts: string[]
  onSelectPrompt: (prompt: string) => void
}

export default function ChatEmptyState({ prompts, onSelectPrompt }: ChatEmptyStateProps) {
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-6 text-center">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/30">
          <Sparkles className="h-8 w-8 text-white" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">开始一次知识库问答</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">支持多轮对话、SSE 流式输出、检索过程追踪与 Markdown 回答渲染。</p>
      </motion.div>
      <div className="mt-8 grid w-full gap-3 sm:grid-cols-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSelectPrompt(prompt)}
            className="rounded-xl border border-slate-200 bg-white p-3 text-left text-sm text-slate-600 shadow-sm transition-all hover:-translate-y-0.5 hover:border-indigo-200 hover:text-slate-800"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { BrainCircuit, CircleCheckBig, GraduationCap, RefreshCcw, Target, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'

import {
  createPracticeSession,
  getLearningPath,
  getPracticeSession,
  listMastery,
  listPracticeSessions,
  listReviewCards,
  listWrongQuestions,
  submitPracticeAnswer,
} from '../api'
import type {
  LearningPathItemResponse,
  MasteryRecordResponse,
  PracticeSessionResponse,
  ReviewCardResponse,
  WrongQuestionResponse,
} from '../types'

type PracticeResult = {
  isCorrect: boolean
  correctAnswer?: string | null
  explanation?: string | null
}

type LearningMetricCard = {
  label: string
  value: number
  Icon: LucideIcon
}

export default function LearningCenterPage() {
  const [loading, setLoading] = useState(false)
  const [starting, setStarting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [limit, setLimit] = useState(5)
  const [sessions, setSessions] = useState<PracticeSessionResponse[]>([])
  const [selectedSession, setSelectedSession] = useState<PracticeSessionResponse | null>(null)
  const [wrongQuestions, setWrongQuestions] = useState<WrongQuestionResponse[]>([])
  const [mastery, setMastery] = useState<MasteryRecordResponse[]>([])
  const [reviewCards, setReviewCards] = useState<ReviewCardResponse[]>([])
  const [learningPath, setLearningPath] = useState<LearningPathItemResponse[]>([])
  const [answer, setAnswer] = useState('')
  const [practiceResult, setPracticeResult] = useState<PracticeResult | null>(null)

  const loadDashboard = async (preserveSessionId?: string | null) => {
    setLoading(true)
    try {
      const [sessionResponse, wrongResponse, masteryResponse, reviewResponse, pathResponse] = await Promise.all([
        listPracticeSessions({ page: 1, page_size: 12 }),
        listWrongQuestions({ page: 1, page_size: 12 }),
        listMastery(),
        listReviewCards({ page: 1, page_size: 12 }),
        getLearningPath(),
      ])

      setSessions(sessionResponse.items)
      setWrongQuestions(wrongResponse.items)
      setMastery(masteryResponse.items)
      setReviewCards(reviewResponse.items)
      setLearningPath(pathResponse.items)

      const nextSessionId = preserveSessionId ?? selectedSession?.id ?? sessionResponse.items[0]?.id ?? null
      if (nextSessionId) {
        const detail = await getPracticeSession(nextSessionId)
        setSelectedSession(detail)
      } else {
        setSelectedSession(null)
      }
    } catch {
      toast.error('加载学习中心数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDashboard()
  }, [])

  const currentQuestion = useMemo(() => {
    if (!selectedSession) return null
    return selectedSession.questions[selectedSession.current_index] ?? null
  }, [selectedSession])

  const metricCards: LearningMetricCard[] = [
    { label: '练习会话', value: sessions.length, Icon: Target },
    { label: '错题条目', value: wrongQuestions.length, Icon: BrainCircuit },
    { label: '掌握度记录', value: mastery.length, Icon: CircleCheckBig },
    { label: '待复习卡片', value: reviewCards.length, Icon: GraduationCap },
  ]

  const startPractice = async () => {
    setStarting(true)
    try {
      const session = await createPracticeSession({ limit })
      setSelectedSession(session)
      setAnswer('')
      setPracticeResult(null)
      toast.success('练习已开始')
      await loadDashboard(session.id)
    } catch {
      toast.error('无法开始练习，当前题库可能没有可用题目')
    } finally {
      setStarting(false)
    }
  }

  const submitAnswer = async () => {
    if (!selectedSession || !currentQuestion || !answer.trim()) {
      toast.error('请先输入答案')
      return
    }
    setSubmitting(true)
    try {
      const response = await submitPracticeAnswer(selectedSession.id, {
        question_id: currentQuestion.id,
        answer: answer.trim(),
      })
      setSelectedSession(response.session)
      setPracticeResult({
        isCorrect: response.attempt.is_correct,
        correctAnswer: response.attempt.correct_answer,
        explanation: response.attempt.explanation,
      })
      setAnswer('')
      await loadDashboard(response.session.id)
    } catch {
      toast.error('提交答案失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6 p-4 lg:p-6">
      <div className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">学习中心</h1>
          <p className="mt-1 text-sm text-slate-500">围绕练习、错题、掌握度和复习卡片形成闭环。</p>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="number"
            min={1}
            max={20}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value) || 5)}
            className="h-10 w-24 rounded-xl border border-slate-200 px-3 text-sm"
          />
          <button
            onClick={() => void startPractice()}
            disabled={starting}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            <GraduationCap className="h-4 w-4" />
            {starting ? '创建中...' : '开始练习'}
          </button>
          <button
            onClick={() => void loadDashboard()}
            className="rounded-xl border border-slate-200 bg-slate-50 p-2 text-slate-600 hover:border-indigo-200 hover:text-indigo-600"
          >
            <RefreshCcw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metricCards.map(({ label, value, Icon }) => {
          return (
            <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">{label}</p>
                  <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 text-indigo-600">
                  <Icon className="h-5 w-5" />
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <section className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">最近练习</h2>
            <div className="space-y-3">
              {sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => void getPracticeSession(session.id).then(setSelectedSession).catch(() => toast.error('加载练习详情失败'))}
                  className={`w-full rounded-xl border px-3 py-3 text-left ${
                    selectedSession?.id === session.id ? 'border-indigo-200 bg-indigo-50' : 'border-slate-200 bg-white hover:bg-slate-50'
                  }`}
                >
                  <p className="text-sm font-semibold text-slate-800">{session.title}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {session.correct_count}/{session.total_questions} · score={(session.score * 100).toFixed(0)}%
                  </p>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">错题本</h2>
            <div className="space-y-3">
              {wrongQuestions.map((item) => (
                <div key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-sm font-medium text-slate-800">{item.question_text}</p>
                  <p className="mt-1 text-xs text-slate-500">错误次数：{item.wrong_count}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">当前练习</h2>
            {!selectedSession ? (
              <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
                还没有练习会话，先创建一轮练习。
              </div>
            ) : currentQuestion ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">
                    第 {selectedSession.current_index + 1} / {selectedSession.total_questions} 题
                  </p>
                  <p className="mt-2 text-base font-medium text-slate-900">{currentQuestion.question_text}</p>
                  {currentQuestion.options && currentQuestion.options.length > 0 && (
                    <div className="mt-3 grid gap-2">
                      {currentQuestion.options.map((option) => (
                        <button
                          key={option.label}
                          onClick={() => setAnswer(option.label)}
                          className={`rounded-xl border px-3 py-2 text-left text-sm ${
                            answer === option.label ? 'border-indigo-300 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                          }`}
                        >
                          {option.label}. {option.text}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <textarea
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  placeholder="输入你的答案"
                  rows={4}
                  className="w-full rounded-xl border border-slate-200 p-3 text-sm"
                />
                <button
                  onClick={() => void submitAnswer()}
                  disabled={submitting}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {submitting ? '提交中...' : '提交答案'}
                </button>
                {practiceResult && (
                  <div className={`rounded-xl border px-4 py-3 ${practiceResult.isCorrect ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
                    <p className="text-sm font-semibold text-slate-900">
                      {practiceResult.isCorrect ? '回答正确' : `回答不正确，正确答案：${practiceResult.correctAnswer || '未提供'}`}
                    </p>
                    {practiceResult.explanation && <p className="mt-2 text-sm text-slate-600">{practiceResult.explanation}</p>}
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
                当前练习已完成，本轮得分 {(selectedSession.score * 100).toFixed(0)}%。
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">复习卡片</h2>
              <div className="space-y-3">
                {reviewCards.map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-sm font-medium text-slate-800">{item.question_text}</p>
                    <p className="mt-1 text-xs text-slate-500">到期时间：{new Date(item.due_at).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">学习路径</h2>
              <div className="space-y-3">
                {learningPath.map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="text-sm font-medium text-slate-800">{item.title}</p>
                    <p className="mt-1 text-xs text-slate-500">优先级：{item.priority} · 状态：{item.status}</p>
                    {item.reason && <p className="mt-2 text-xs text-slate-600">{item.reason}</p>}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-slate-900">掌握度</h2>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {mastery.map((item) => (
                <div key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-sm font-medium text-slate-800">
                    记录 {item.question_id || item.knowledge_point_id || item.id}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    score={(item.mastery_score * 100).toFixed(0)}% · attempts={item.attempts_count} · correct={item.correct_count}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

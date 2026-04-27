import type { QuestionCreate, QuestionOption, QuestionResponse, QuestionType, QuestionUpdate } from '../../types'

export const QUESTION_OPTION_LABELS = ['A', 'B', 'C', 'D'] as const

export type QuestionOptionLabel = (typeof QUESTION_OPTION_LABELS)[number]
export type TrueFalseAnswer = 'true' | 'false'

export interface QuestionEditorFormState {
  questionText: string
  questionType: QuestionType
  optionTexts: Record<QuestionOptionLabel, string>
  singleAnswer: QuestionOptionLabel | ''
  multipleAnswers: QuestionOptionLabel[]
  trueFalseAnswer: TrueFalseAnswer | ''
  shortAnswer: string
  explanation: string
}

const emptyOptionTexts = (): Record<QuestionOptionLabel, string> => ({
  A: '',
  B: '',
  C: '',
  D: '',
})

export const createEmptyQuestionEditorState = (questionType: QuestionType = 'single'): QuestionEditorFormState => ({
  questionText: '',
  questionType,
  optionTexts: emptyOptionTexts(),
  singleAnswer: '',
  multipleAnswers: [],
  trueFalseAnswer: '',
  shortAnswer: '',
  explanation: '',
})

export const questionToEditorState = (question: QuestionResponse): QuestionEditorFormState => {
  const optionTexts = emptyOptionTexts()
  for (const option of question.options ?? []) {
    if (option.label in optionTexts) {
      optionTexts[option.label as QuestionOptionLabel] = option.text
    }
  }

  return {
    questionText: question.question_text,
    questionType: question.question_type,
    optionTexts,
    singleAnswer: question.question_type === 'single' && isOptionLabel(question.answer) ? question.answer : '',
    multipleAnswers:
      question.question_type === 'multiple'
        ? parseMultipleAnswer(question.answer)
        : [],
    trueFalseAnswer:
      question.question_type === 'true_false' && (question.answer === 'true' || question.answer === 'false')
        ? question.answer
        : '',
    shortAnswer: question.question_type === 'short_answer' ? question.answer ?? '' : '',
    explanation: question.explanation ?? '',
  }
}

export const changeEditorType = (
  state: QuestionEditorFormState,
  questionType: QuestionType
): QuestionEditorFormState => {
  if (state.questionType === questionType) {
    return state
  }

  if (questionType === 'single' || questionType === 'multiple') {
    return {
      ...state,
      questionType,
      optionTexts: ensureChoiceOptionSeed(state.optionTexts),
      singleAnswer: questionType === 'single' ? state.singleAnswer : '',
      multipleAnswers: questionType === 'multiple' ? state.multipleAnswers : [],
      trueFalseAnswer: '',
      shortAnswer: '',
    }
  }

  return {
    ...state,
    questionType,
    optionTexts: emptyOptionTexts(),
    singleAnswer: '',
    multipleAnswers: [],
    trueFalseAnswer: questionType === 'true_false' ? state.trueFalseAnswer : '',
    shortAnswer: questionType === 'short_answer' ? state.shortAnswer : '',
  }
}

export const buildQuestionWritePayload = (
  state: QuestionEditorFormState
): { error?: string; payload?: Omit<QuestionCreate, 'bank_id' | 'knowledge_point_ids'> & Partial<QuestionUpdate> } => {
  const questionText = state.questionText.trim()
  if (!questionText) {
    return { error: '题干不能为空' }
  }

  const explanation = state.explanation.trim() || undefined

  if (state.questionType === 'single' || state.questionType === 'multiple') {
    const optionsResult = buildChoiceOptions(state.optionTexts)
    if (optionsResult.error) {
      return { error: optionsResult.error }
    }

    const validLabels = optionsResult.payload.map((item) => item.label)
    if (state.questionType === 'single') {
      if (!state.singleAnswer || !validLabels.includes(state.singleAnswer)) {
        return { error: '单选题答案必须从已填写的 A/B/C/D 选项中选择一个' }
      }
      return {
        payload: {
          question_text: questionText,
          question_type: state.questionType,
          options: optionsResult.payload,
          answer: state.singleAnswer,
          explanation,
        },
      }
    }

    const normalizedAnswers = normalizeMultipleAnswers(state.multipleAnswers, validLabels)
    if (normalizedAnswers.length < 2) {
      return { error: '多选题至少需要选择两个答案' }
    }

    return {
      payload: {
        question_text: questionText,
        question_type: state.questionType,
        options: optionsResult.payload,
        answer: normalizedAnswers.join(','),
        explanation,
      },
    }
  }

  if (state.questionType === 'true_false') {
    if (!state.trueFalseAnswer) {
      return { error: '判断题必须选择“对”或“错”' }
    }
    return {
      payload: {
        question_text: questionText,
        question_type: state.questionType,
        options: null,
        answer: state.trueFalseAnswer,
        explanation,
      },
    }
  }

  const shortAnswer = state.shortAnswer.trim()
  if (!shortAnswer) {
    return { error: '简答题答案不能为空' }
  }

  return {
    payload: {
      question_text: questionText,
      question_type: state.questionType,
      options: null,
      answer: shortAnswer,
      explanation,
    },
  }
}

export const formatQuestionAnswer = (question: QuestionResponse): string | null => {
  if (!question.answer) return null
  if (question.question_type === 'true_false') {
    return question.answer === 'true' ? '对' : question.answer === 'false' ? '错' : question.answer
  }
  if (question.question_type === 'multiple') {
    return question.answer.split(',').map((item) => item.trim()).filter(Boolean).join('、')
  }
  return question.answer
}

const buildChoiceOptions = (
  optionTexts: Record<QuestionOptionLabel, string>
): { error?: string; payload: QuestionOption[] } => {
  const payload: QuestionOption[] = []
  let encounteredBlank = false

  for (const label of QUESTION_OPTION_LABELS) {
    const text = optionTexts[label].trim()
    if (!text) {
      encounteredBlank = true
      continue
    }
    if (encounteredBlank) {
      return { error: '选项必须按 A/B/C/D 连续填写，不能跳空', payload: [] }
    }
    payload.push({ label, text })
  }

  if (payload.length < 2) {
    return { error: '单选题或多选题至少需要填写两个选项', payload: [] }
  }

  return { payload }
}

const normalizeMultipleAnswers = (answers: QuestionOptionLabel[], validLabels: QuestionOptionLabel[]) => {
  const unique = Array.from(new Set(answers.filter((answer) => validLabels.includes(answer))))
  return QUESTION_OPTION_LABELS.filter((label) => unique.includes(label))
}

const parseMultipleAnswer = (answer: string | null): QuestionOptionLabel[] => {
  if (!answer) return []
  const tokens = answer
    .split(',')
    .map((item) => item.trim().toUpperCase())
    .filter((item): item is QuestionOptionLabel => isOptionLabel(item))
  return Array.from(new Set(tokens)).sort(
    (left, right) => QUESTION_OPTION_LABELS.indexOf(left) - QUESTION_OPTION_LABELS.indexOf(right)
  )
}

const ensureChoiceOptionSeed = (optionTexts: Record<QuestionOptionLabel, string>) => {
  const next = { ...optionTexts }
  if (!next.A) next.A = ''
  if (!next.B) next.B = ''
  return next
}

const isOptionLabel = (value: string | null | undefined): value is QuestionOptionLabel =>
  value !== null && value !== undefined && QUESTION_OPTION_LABELS.includes(value as QuestionOptionLabel)

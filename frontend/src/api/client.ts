/** 后端接口客户端：统一错误体、JSON 请求与 SSE 事件解析。 */

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string; details?: unknown }
}

export class ApiError extends Error {
  code: string
  status: number

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export interface AnalyticsOverview {
  questions: number
  questions_week: number
  questions_month: number
  pending_approvals: number
  tool_calls: number
  completion_rate: number
  mode_split: { rag: number; agent: number }
  daily: { date: string; count: number }[]
  hot_questions: { question: string; count: number }[]
  chapter_focus: { label: string; value: number }[]
  top_documents: { title: string; count: number }[]
  documents: { count: number; chunks: number }
}

export interface PracticeOption {
  key: string
  text: string
}

export interface PracticeQuestion {
  id: string
  chapter_id: string
  chapter_title: string
  concept_id: string | null
  type: 'single' | 'judge'
  stem: string
  options: PracticeOption[]
  difficulty: string
}

export interface AttemptResult {
  attempt_id: string
  correct: boolean
  given: string
  expected: string
  explanation: string
  source: string
  stats: { total: number; correct: number; rate: number }
}

const BASE = '/api/v2'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(
      response.status,
      body?.error?.code ?? 'HTTP_ERROR',
      body?.error?.message ?? `请求失败（${response.status}）`,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export interface RunEventPayload {
  run_id: string
  seq: number
  [key: string]: unknown
}

export type RunEventHandler = (type: string, payload: RunEventPayload) => void

/** 读取 SSE：按空行切分事件块，支持 after_seq 续传与 AbortSignal 取消。 */
export async function streamRunEvents(
  runId: string,
  onEvent: RunEventHandler,
  options: { afterSeq?: number; signal?: AbortSignal } = {},
): Promise<void> {
  const response = await fetch(
    `${BASE}/runs/${runId}/events?after_seq=${options.afterSeq ?? 0}`,
    { signal: options.signal, headers: { Accept: 'text/event-stream' } },
  )
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, 'SSE_FAILED', '事件流连接失败')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let index = buffer.indexOf('\n\n')
    while (index >= 0) {
      const block = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (data) {
        try {
          onEvent(event, JSON.parse(data) as RunEventPayload)
        } catch {
          // 单条事件解析失败不中断整条流
        }
      }
      index = buffer.indexOf('\n\n')
    }
  }
}

export interface SessionSummary {
  id: string
  course_id: string
  title: string
  last_run: { run_id: string; question: string; status: string; mode: string; created_at: string } | null
}

export interface RunDetail {
  run_id: string
  session_id: string
  status: string
  question: string
  answer_markdown: string
  citations: Evidence[]
  cards: Card[]
  pending_input: PendingInput | null
  error_code: string | null
  latest_seq: number
}

export interface Evidence {
  chunk_id: string
  document_id: string
  title: string
  locator: { section_path: string[]; page: number | null }
  excerpt: string
  channels: string[]
  score: number
}

export interface Card {
  type: string
  tool?: string
  title?: string
  data?: Record<string, unknown>
}

export interface PendingInput {
  input_id: string
  kind: string
  prompt: string
  tool_call_id?: string
  args_hash?: string
}

export interface DocumentSummary {
  id: string
  title: string
  filename: string
  mime: string
  size: number
  status: string
  chunk_count: number
  chapter_id: string | null
  created_at: string
}

export interface GraphNodeDto {
  id: string
  name: string
  category: number
  desc: string
  chapter_id: string | null
}

export interface GraphLinkDto {
  source: string
  target: string
  kind: 'prerequisite' | 'contains' | 'related'
}

export interface GraphDto {
  nodes: GraphNodeDto[]
  links: GraphLinkDto[]
  chapters: { id: string; title: string }[]
}

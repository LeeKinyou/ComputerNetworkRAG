import { computed, ref } from 'vue'

export interface StudentOption {
  key: string
  name: string
  initial: string
  note: string
}

/** 演示用的学生名单：多身份的目的只是让「做题 → 画像 → 问答」在多人之间也能对上。 */
export const STUDENT_OPTIONS: StudentOption[] = [
  { key: 'demo_user', name: '李金阳', initial: '李', note: '主账号' },
  { key: 'stu_lin', name: '林晓', initial: '林', note: '示例学生 · 基础偏弱' },
  { key: 'stu_zhao', name: '赵一鸣', initial: '赵', note: '示例学生 · 基础较好' },
]

const STORAGE_KEY = 'cnrag.student'
const FALLBACK = STUDENT_OPTIONS[0]

function readStored(): string {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored && STUDENT_OPTIONS.some((item) => item.key === stored) ? stored : FALLBACK.key
}

const currentKey = ref(readStored())
const current = computed(() => STUDENT_OPTIONS.find((item) => item.key === currentKey.value) ?? FALLBACK)

/** 学生会话下钉死自己的 key：localStorage 被改也不会去请求别人的数据。 */
let lockedKey: string | null = null

export function lockStudent(key: string) {
  if (!STUDENT_OPTIONS.some((item) => item.key === key)) return
  lockedKey = key
  currentKey.value = key
  localStorage.setItem(STORAGE_KEY, key)
}

export function unlockStudent() {
  lockedKey = null
}

export function setStudent(key: string) {
  if (lockedKey) return
  if (!STUDENT_OPTIONS.some((item) => item.key === key) || key === currentKey.value) return
  currentKey.value = key
  localStorage.setItem(STORAGE_KEY, key)
}

export function useStudent() {
  return { currentKey, current, students: STUDENT_OPTIONS, setStudent }
}

import { computed, ref } from 'vue'
import { api } from '@/api/client'

export interface StudentOption {
  key: string
  name: string
  initial: string
  note: string
}

export interface UserRow {
  user_key: string
  display_name: string
  role: string
  note: string
}

const STORAGE_KEY = 'cnrag.student'

/** 名单来自后端 `/users`，姓名不再写死在前端。 */
const students = ref<StudentOption[]>([])
const currentKey = ref('')

const EMPTY: StudentOption = { key: '', name: '', initial: '', note: '' }

const current = computed(
  () => students.value.find((item) => item.key === currentKey.value) ?? students.value[0] ?? EMPTY,
)

/** 学生登录后钉死自己的 key：localStorage 被改也不会去请求别人的数据。 */
let lockedKey: string | null = null

function toOption(row: UserRow): StudentOption {
  return {
    key: row.user_key,
    name: row.display_name || row.user_key,
    initial: (row.display_name || row.user_key).slice(0, 1),
    note: row.note,
  }
}

/** 拉取账号名单：教师拿到全部学生，学生只会拿到自己。 */
export async function loadStudents(): Promise<void> {
  const stored = localStorage.getItem(STORAGE_KEY) ?? ''
  try {
    const res = await api.get<{ items: UserRow[] }>('/users')
    students.value = res.items.filter((row) => row.role === 'student').map(toOption)
  } catch {
    // 名单拉不到时保留已有内容，不让页面整体失败
  }
  if (!students.value.length) return
  if (lockedKey && students.value.some((item) => item.key === lockedKey)) {
    currentKey.value = lockedKey
  } else if (stored && students.value.some((item) => item.key === stored)) {
    currentKey.value = stored
  } else {
    currentKey.value = students.value[0].key
  }
}

export function lockStudent(key: string, name?: string) {
  lockedKey = key
  if (!students.value.some((item) => item.key === key)) {
    students.value = [
      { key, name: name || key, initial: (name || key).slice(0, 1), note: '' },
      ...students.value,
    ]
  }
  currentKey.value = key
  localStorage.setItem(STORAGE_KEY, key)
}

export function unlockStudent() {
  lockedKey = null
}

export function resetStudent() {
  lockedKey = null
  if (students.value.length) currentKey.value = students.value[0].key
}

export function setStudent(key: string) {
  if (lockedKey) return
  if (!students.value.some((item) => item.key === key) || key === currentKey.value) return
  currentKey.value = key
  localStorage.setItem(STORAGE_KEY, key)
}

export function useStudent() {
  return { currentKey, current, students, setStudent }
}

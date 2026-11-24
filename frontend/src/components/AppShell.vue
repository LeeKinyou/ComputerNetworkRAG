<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  BarChart3,
  BookMarked,
  BookOpen,
  Bot,
  ChevronDown,
  ClipboardList,
  HelpCircle,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Menu,
  Moon,
  PenLine,
  Route as RouteIcon,
  Search,
  Sparkles,
  Sun,
  TrendingUp,
  UserRound,
  Waypoints,
  X,
} from 'lucide-vue-next'
import { api } from '@/api/client'
import { useAuth } from '@/composables/useAuth'
import { useTheme } from '@/composables/useTheme'
import { useStudent } from '@/composables/useStudent'

const route = useRoute()
const router = useRouter()
const { currentKey, current, students, setStudent } = useStudent()
const { user, authEnabled, logout } = useAuth()

const isTeacher = computed(() => user.value?.role === 'teacher')
/** 教师可切学生；关闭鉴权的本地演示模式也保留下拉。 */
const canSwitch = computed(() => isTeacher.value || !authEnabled.value)

function onStudentChange(event: Event) {
  setStudent((event.target as HTMLSelectElement).value)
}

async function onLogout() {
  drawerOpen.value = false
  await logout()
  await router.replace({ path: '/login' })
}
const { isDark, toggle } = useTheme()

const navGroups = computed(() => {
  const groups = [
    {
      title: '',
      items: [
        { to: '/', label: '工作台', icon: LayoutDashboard },
        { to: '/chat', label: '智能问答', icon: Bot },
        { to: '/assignments', label: '作业', icon: ClipboardList },
        { to: '/practice', label: '练习中心', icon: PenLine },
        { to: '/wrongbook', label: '错题本', icon: BookMarked },
        { to: '/graph', label: '知识图谱', icon: Waypoints },
        { to: '/path', label: '学习计划', icon: RouteIcon },
        { to: '/documents', label: '知识库', icon: BookOpen },
        { to: '/progress', label: '学习报告', icon: TrendingUp },
        { to: '/profile', label: '我的', icon: UserRound },
      ],
    },
  ]
  if (isTeacher.value) {
    groups.push({
      title: '教师视图',
      items: [{ to: '/insights', label: '学情分析', icon: BarChart3 }],
    })
  }
  return groups
})

/** 手机底部标签栏：只放最高频的五个入口，其余走「更多」抽屉。 */
const tabs = [
  { to: '/', label: '工作台', icon: LayoutDashboard },
  { to: '/chat', label: '问答', icon: Bot },
  { to: '/assignments', label: '作业', icon: ClipboardList },
  { to: '/practice', label: '练习', icon: PenLine },
  { to: '/profile', label: '我的', icon: UserRound },
]

const labels: Record<string, string> = {
  overview: '工作台',
  chat: '智能问答',
  assignments: '作业',
  practice: '练习中心',
  graph: '知识图谱',
  path: '学习计划',
  documents: '知识库',
  wrongbook: '错题本',
  progress: '学习报告',
  insights: '学情分析',
  profile: '我的',
}

const currentLabel = computed(() => labels[String(route.name)] ?? '工作台')
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))

function navClass(to: string, size: 'desktop' | 'drawer') {
  const active = isActive(to)
  const base =
    size === 'drawer'
      ? 'flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] transition-colors'
      : 'flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition-all duration-200'
  return [
    base,
    active
      ? 'bg-surface font-medium text-ink shadow-[0_1px_2px_rgba(16,24,40,0.04)]'
      : 'text-subink/85 hover:bg-tint hover:text-ink',
  ]
}

/** 手机抽屉导航：从左侧滑出，承载桌面侧栏里的全部入口。 */
const drawerOpen = ref(false)
watch(
  () => route.fullPath,
  () => (drawerOpen.value = false),
)

interface ConceptHit {
  id: string
  name: string
  desc: string
  chapter: string
}

const paletteOpen = ref(false)
const keyword = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const concepts = ref<ConceptHit[]>([])

async function ensureConcepts() {
  if (concepts.value.length) return
  try {
    const graph = await api.get<{
      nodes: { id: string; name: string; desc?: string; chapter_id?: string }[]
      chapters: { id: string; title: string }[]
    }>('/courses/course_cn/graph')
    const titles: Record<string, string> = {}
    for (const chapter of graph.chapters ?? []) titles[chapter.id] = chapter.title
    concepts.value = (graph.nodes ?? []).map((node) => ({
      id: node.id,
      name: node.name,
      desc: node.desc ?? '',
      chapter: titles[node.chapter_id ?? ''] ?? '',
    }))
  } catch {
    concepts.value = []
  }
}

const hits = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return concepts.value.slice(0, 6)
  return concepts.value
    .filter((item) => item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q))
    .slice(0, 8)
})

watch(keyword, () => (activeIndex.value = 0))

async function openPalette() {
  drawerOpen.value = false
  paletteOpen.value = true
  keyword.value = ''
  activeIndex.value = 0
  void ensureConcepts()
  await nextTick()
  inputRef.value?.focus()
}

function closePalette() {
  paletteOpen.value = false
}

function goConcept(hit: ConceptHit) {
  closePalette()
  router.push({ path: '/graph', query: { focus: hit.id } })
}

function onPaletteKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closePalette()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, hits.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (event.key === 'Enter' && hits.value[activeIndex.value]) {
    event.preventDefault()
    goConcept(hits.value[activeIndex.value])
  }
}

// Ctrl + K 唤出搜索；Esc 关闭抽屉。不拦截其他快捷键
function onGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && drawerOpen.value) drawerOpen.value = false
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (paletteOpen.value) closePalette()
    else void openPalette()
  }
}

// 左下角运行环境标识：按 /health 的真实后端显示，不写死 SQLite
const dbBackend = ref('')
const backendTitle = computed(() => {
  if (dbBackend.value === 'postgresql') return 'PostgreSQL · 单进程'
  if (dbBackend.value === 'sqlite') return 'SQLite · 单进程'
  return '单进程 · 单端口'
})
async function loadHealth() {
  try {
    const health = await api.get<{ db_backend?: string }>('/health')
    dbBackend.value = health.db_backend ?? ''
  } catch {
    dbBackend.value = ''
  }
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalKeydown)
  void loadHealth()
})
onUnmounted(() => window.removeEventListener('keydown', onGlobalKeydown))
</script>

<template>
  <div class="flex h-full min-h-0 flex-col lg:flex-row">
    <aside class="hidden w-[236px] shrink-0 flex-col border-r border-line bg-shell lg:flex">
      <div class="flex h-14 items-center gap-2.5 px-4">
        <div
          class="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-white shadow-[0_5px_14px_-4px_rgba(47,107,255,0.55)]"
        >
          <Sparkles :size="16" />
        </div>
        <div class="leading-tight">
          <div class="text-[12.5px] font-semibold tracking-tight">智网系统</div>
          <div class="text-[11px] text-muted">智能助教工作台</div>
        </div>
      </div>

      <nav class="flex flex-col gap-0.5 p-2.5">
        <template v-for="(group, gi) in navGroups" :key="gi">
          <div v-if="group.title" class="mt-2 border-t border-line px-1 pb-1 pt-3">
            <p class="px-2 text-[9px] tracking-[0.08em] text-muted">{{ group.title }}</p>
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            :class="navClass(item.to, 'desktop')"
          >
            <component
              :is="item.icon"
              :size="16"
              :stroke-width="1.8"
              :class="isActive(item.to) ? 'text-brand' : ''"
            />
            {{ item.label }}
          </RouterLink>
        </template>
      </nav>

      <div class="mt-auto px-4 py-3">
        <div class="flex items-center gap-1.5 text-[10.5px] text-muted">
          <span class="h-1.5 w-1.5 rounded-full bg-success" />
          {{ backendTitle }}
        </div>
      </div>
    </aside>

    <main class="flex min-h-0 min-w-0 flex-1 flex-col">
      <header
        class="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-line bg-surface/65 px-3 backdrop-blur-xl sm:px-6"
      >
        <div class="flex min-w-0 items-center gap-2 text-[12.5px] text-muted">
          <button class="icon-btn -ml-1.5 shrink-0 lg:hidden" aria-label="打开导航" @click="drawerOpen = true">
            <Menu :size="18" />
          </button>
          <span class="hidden sm:inline">计算机网络</span>
          <span class="hidden text-line-strong sm:inline">/</span>
          <span class="truncate font-medium text-ink">{{ currentLabel }}</span>
        </div>

        <div class="flex shrink-0 items-center gap-1 sm:gap-1.5">
          <button
            class="flex h-8 items-center gap-2 rounded-full bg-tint px-2.5 text-[12px] text-muted transition-colors hover:bg-tint-strong hover:text-subink sm:px-3"
            aria-label="搜索知识点"
            @click="openPalette"
          >
            <Search :size="13.5" />
            <span class="hidden sm:inline">搜索知识点</span>
            <kbd class="hidden rounded-md bg-surface px-1.5 py-0.5 text-[10px] text-muted lg:inline">Ctrl K</kbd>
          </button>
          <button
            class="icon-btn hidden sm:inline-flex"
            :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
            @click="toggle"
          >
            <Sun v-if="isDark" :size="16" />
            <Moon v-else :size="16" />
          </button>
          <button class="icon-btn hidden sm:inline-flex" aria-label="帮助"><HelpCircle :size="16" /></button>
          <label
            v-if="canSwitch"
            class="flex h-7 min-w-0 items-center gap-1.5 rounded-full bg-brand-soft pl-1 pr-1.5 sm:ml-1"
            :title="isTeacher ? `教师 · 可切换学生` : current.note"
          >
            <span class="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand text-[10px] font-semibold text-white">
              {{ isTeacher ? '师' : current.initial }}
            </span>
            <select
              :value="currentKey"
              aria-label="切换当前学生"
              class="h-7 max-w-[68px] cursor-pointer appearance-none truncate bg-transparent pr-3 text-[11px] font-semibold text-brand outline-none sm:max-w-none"
              @change="onStudentChange"
            >
              <option v-for="s in students" :key="s.key" :value="s.key">{{ s.name }}</option>
            </select>
            <ChevronDown :size="11" class="-ml-3.5 shrink-0 text-brand" />
          </label>
          <span
            v-else
            class="ml-1 flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-brand-soft pl-1 pr-2.5"
            :title="current.note"
          >
            <span class="grid h-5 w-5 place-items-center rounded-full bg-brand text-[10px] font-semibold text-white">
              {{ current.initial }}
            </span>
            <span class="text-[11px] font-semibold text-brand">{{ current.name }}</span>
          </span>
          <button
            v-if="authEnabled && user"
            class="icon-btn hidden sm:inline-flex"
            aria-label="退出登录"
            title="退出登录"
            @click="onLogout"
          >
            <LogOut :size="16" />
          </button>
        </div>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <slot />
      </div>
    </main>

    <!-- 手机底部标签栏：随布局占位，不遮挡内容与问答输入框 -->
    <nav class="safe-bottom shrink-0 border-t border-line bg-surface/95 backdrop-blur-xl lg:hidden">
      <div class="flex items-stretch">
        <RouterLink
          v-for="tab in tabs"
          :key="tab.to"
          :to="tab.to"
          class="flex flex-1 flex-col items-center justify-center gap-1 py-1.5 transition-colors"
          :class="isActive(tab.to) ? 'text-brand' : 'text-muted'"
        >
          <component :is="tab.icon" :size="19" :stroke-width="isActive(tab.to) ? 2.1 : 1.8" />
          <span class="text-[10.5px] leading-none">{{ tab.label }}</span>
        </RouterLink>
        <button
          class="flex flex-1 flex-col items-center justify-center gap-1 py-1.5 text-muted transition-colors"
          aria-label="全部功能"
          @click="drawerOpen = true"
        >
          <LayoutGrid :size="19" :stroke-width="1.8" />
          <span class="text-[10.5px] leading-none">更多</span>
        </button>
      </div>
    </nav>

    <!-- 手机抽屉：完整导航 + 主题 / 身份 / 退出 -->
    <div
      v-if="drawerOpen"
      class="fixed inset-0 z-50 lg:hidden"
      role="dialog"
      aria-label="导航"
    >
      <div class="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" @click="drawerOpen = false" />
      <aside
        class="absolute inset-y-0 left-0 flex w-[82%] max-w-[320px] flex-col border-r border-line bg-shell shadow-[0_0_40px_rgba(16,24,40,0.25)]"
      >
        <div class="flex items-center justify-between px-4 pb-2 pt-4">
          <div class="flex items-center gap-2.5">
            <div
              class="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-white shadow-[0_5px_14px_-4px_rgba(47,107,255,0.55)]"
            >
              <Sparkles :size="16" />
            </div>
            <div class="leading-tight">
              <div class="text-[12.5px] font-semibold tracking-tight">智网系统</div>
              <div class="text-[11px] text-muted">智能助教工作台</div>
            </div>
          </div>
          <button class="icon-btn" aria-label="关闭导航" @click="drawerOpen = false">
            <X :size="16" />
          </button>
        </div>

        <nav class="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 pb-3">
          <template v-for="(group, gi) in navGroups" :key="gi">
            <div v-if="group.title" class="mt-2 border-t border-line px-1 pb-1 pt-3">
              <p class="px-3 text-[9.5px] tracking-[0.08em] text-muted">{{ group.title }}</p>
            </div>
            <RouterLink
              v-for="item in group.items"
              :key="item.to"
              :to="item.to"
              :class="navClass(item.to, 'drawer')"
              @click="drawerOpen = false"
            >
              <component
                :is="item.icon"
                :size="17"
                :stroke-width="1.8"
                :class="isActive(item.to) ? 'text-brand' : ''"
              />
              {{ item.label }}
            </RouterLink>
          </template>
        </nav>

        <div class="safe-bottom shrink-0 space-y-1 border-t border-line px-3 py-3">
          <div class="flex items-center justify-between rounded-xl px-2 py-1.5">
            <div class="flex items-center gap-2 text-[12.5px] text-subink">
              <Sun v-if="isDark" :size="15" class="text-muted" />
              <Moon v-else :size="15" class="text-muted" />
              {{ isDark ? '切到浅色模式' : '切到深色模式' }}
            </div>
            <button
              class="flex h-7 w-11 items-center rounded-full px-1 transition-colors"
              :class="isDark ? 'justify-end bg-brand' : 'justify-start bg-line-strong'"
              :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
              @click="toggle"
            >
              <span class="h-5 w-5 rounded-full bg-surface shadow-sm" />
            </button>
          </div>

          <label
            v-if="canSwitch"
            class="flex items-center justify-between rounded-xl px-2 py-1.5"
          >
            <span class="text-[12.5px] text-subink">{{ isTeacher ? '切换查看的学生' : '当前学生' }}</span>
            <span class="flex h-7 items-center gap-1.5 rounded-full bg-brand-soft pl-1 pr-1.5">
              <span class="grid h-5 w-5 place-items-center rounded-full bg-brand text-[10px] font-semibold text-white">
                {{ isTeacher ? '师' : current.initial }}
              </span>
              <select
                :value="currentKey"
                class="h-7 cursor-pointer appearance-none bg-transparent pr-3 text-[11.5px] font-semibold text-brand outline-none"
                aria-label="切换当前学生"
                @change="onStudentChange"
              >
                <option v-for="s in students" :key="s.key" :value="s.key">{{ s.name }}</option>
              </select>
              <ChevronDown :size="11" class="-ml-3.5 text-brand" />
            </span>
          </label>

          <button
            v-if="authEnabled && user"
            class="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-[12.5px] text-subink transition-colors hover:bg-tint"
            @click="onLogout"
          >
            <LogOut :size="15" class="text-muted" />
            退出登录
          </button>

          <div class="flex items-center gap-1.5 px-2 pt-1 text-[10.5px] text-muted">
            <span class="h-1.5 w-1.5 rounded-full bg-success" />
            {{ backendTitle }}
          </div>
        </div>
      </aside>
    </div>

    <div
      v-if="paletteOpen"
      class="fixed inset-0 z-50 flex items-start justify-center bg-ink/25 px-3 pt-[9vh] backdrop-blur-[2px] sm:px-4 sm:pt-[12vh]"
      @click.self="closePalette"
    >
      <div class="w-full max-w-[560px] overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_24px_60px_-18px_rgba(16,24,40,0.35)]">
        <div class="flex items-center gap-2.5 border-b border-line px-4 py-3">
          <Search :size="15" class="text-muted" />
          <input
            ref="inputRef"
            v-model="keyword"
            class="h-7 min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted"
            placeholder="搜知识点，回车跳到图谱定位"
            @keydown="onPaletteKeydown"
          />
          <kbd class="hidden rounded-md bg-tint px-1.5 py-0.5 text-[10px] text-muted sm:inline">Esc</kbd>
        </div>
        <ul v-if="hits.length" class="max-h-[320px] overflow-y-auto p-1.5">
          <li
            v-for="(hit, i) in hits"
            :key="hit.id"
            class="flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2.5"
            :class="i === activeIndex ? 'bg-tint' : 'hover:bg-tint-soft'"
            @mouseenter="activeIndex = i"
            @click="goConcept(hit)"
          >
            <div class="min-w-0">
              <p class="truncate text-[12.5px] font-medium text-ink">{{ hit.name }}</p>
              <p class="mt-0.5 truncate text-[10px] text-muted">{{ hit.desc || hit.chapter }}</p>
            </div>
            <span class="hidden shrink-0 rounded-full bg-tint-soft px-2 py-0.5 text-[9.5px] text-muted sm:inline">
              {{ hit.chapter }}
            </span>
          </li>
        </ul>
        <div v-else class="px-4 py-8 text-center text-[11px] text-muted">
          没找到匹配的知识点，换个关键词试试
        </div>
        <div class="flex items-center justify-between border-t border-line px-4 py-2 text-[9.5px] text-muted">
          <span>↑↓ 选择 · Enter 定位</span>
          <span class="hidden sm:inline">Ctrl + K 关闭</span>
        </div>
      </div>
    </div>
  </div>
</template>

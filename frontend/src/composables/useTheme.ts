import { ref, watch } from 'vue'

const isDark = ref(false)
let initialized = false

function applyTheme() {
  document.documentElement.classList.toggle('dark', isDark.value)
  document.documentElement.style.colorScheme = isDark.value ? 'dark' : 'light'
  localStorage.setItem('cnrag-theme', isDark.value ? 'dark' : 'light')
}

export function useTheme() {
  if (!initialized && typeof window !== 'undefined') {
    initialized = true
    const saved = localStorage.getItem('cnrag-theme')
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    isDark.value = saved ? saved === 'dark' : prefersDark
    applyTheme()
  }

  function toggle() {
    isDark.value = !isDark.value
  }

  watch(isDark, applyTheme)

  return { isDark, toggle }
}

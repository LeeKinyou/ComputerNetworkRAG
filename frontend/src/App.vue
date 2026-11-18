<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '@/components/AppShell.vue'

const route = useRoute()
const fullscreen = computed(() => route.meta.fullscreen === true)
</script>

<template>
  <RouterView v-if="fullscreen" />
  <AppShell v-else>
    <RouterView />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ToastHost from '@/components/ToastHost.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// The bootstrap cookie persists when the page is opened in a new tab.
// Check the frame as well so the standalone view keeps its navigation.
const embedded = computed(() => window.self !== window.top)

async function handleLogout() {
  const request = auth.logout().then(() => true, () => false)
  await router.replace({ path: '/auth/error', query: { reason: 'logged_out' } })
  if (!await request) {
    await router.replace({ path: '/auth/error', query: { reason: 'logout_failed' } })
  }
}
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell-embedded': embedded }">
    <header
      v-if="!embedded"
      class="app-header"
    >
      <div class="flex items-center gap-3 min-w-0">
        <span class="font-semibold text-gray-900 dark:text-white shrink-0">Ops Extension</span>
        <nav class="flex gap-1 text-sm overflow-x-auto">
          <RouterLink class="nav-link" to="/tickets">我的工单</RouterLink>
          <template v-if="auth.isAdmin">
            <RouterLink class="nav-link" to="/admin/tickets">工单管理</RouterLink>
            <RouterLink class="nav-link" to="/admin/expenses">报账管理</RouterLink>
            <RouterLink class="nav-link" to="/admin/suppliers">主数据</RouterLink>
            <RouterLink class="nav-link" to="/admin/reports">费用报表</RouterLink>
            <RouterLink class="nav-link" to="/admin/manual">手册配置</RouterLink>
          </template>
        </nav>
      </div>
      <div class="text-sm flex items-center gap-3 shrink-0 text-gray-500 dark:text-dark-400">
        <span v-if="auth.me" class="text-gray-700 dark:text-dark-300">{{ auth.me.username }}（{{ auth.me.sub2api_role }}）</span>
        <button
          v-if="auth.me"
          type="button"
          class="btn-ghost btn-sm"
          @click="handleLogout"
        >
          退出
        </button>
      </div>
    </header>
    <main class="app-main">
      <RouterView v-if="auth.me || route.path === '/auth/error'" :key="route.fullPath" />
    </main>
    <ToastHost />
  </div>
</template>

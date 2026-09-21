<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const embedded = computed(() => document.cookie.includes('ops_ui_mode=embedded'))
</script>

<template>
  <div class="min-h-screen flex flex-col bg-dark-900 text-dark-100">
    <header
      v-if="!embedded"
      class="border-b border-dark-700 bg-dark-900 px-4 py-2.5 flex items-center justify-between"
    >
      <div class="flex items-center gap-3 min-w-0">
        <span class="font-semibold tracking-wide text-white shrink-0">Ops Extension</span>
        <nav class="flex gap-1 text-sm overflow-x-auto">
          <RouterLink class="nav-link" to="/tickets">我的工单</RouterLink>
          <template v-if="auth.isAdmin">
            <RouterLink class="nav-link" to="/admin/tickets">工单管理</RouterLink>
            <RouterLink class="nav-link" to="/admin/expenses">报账管理</RouterLink>
            <RouterLink class="nav-link" to="/admin/suppliers">主数据</RouterLink>
            <RouterLink class="nav-link" to="/admin/reports">费用报表</RouterLink>
          </template>
        </nav>
      </div>
      <div class="text-sm flex items-center gap-3 shrink-0 text-dark-400">
        <span v-if="auth.me" class="text-dark-300">{{ auth.me.username }}（{{ auth.me.sub2api_role }}）</span>
        <button
          v-if="auth.me"
          type="button"
          class="btn-ghost btn-sm"
          @click="auth.logout()"
        >
          退出
        </button>
      </div>
    </header>
    <header
      v-else
      class="border-b border-dark-700 bg-dark-900 px-3 py-1.5 flex gap-1 text-sm overflow-x-auto"
    >
      <RouterLink class="nav-link" to="/tickets">我的工单</RouterLink>
      <template v-if="auth.isAdmin">
        <RouterLink class="nav-link" to="/admin/tickets">工单管理</RouterLink>
        <RouterLink class="nav-link" to="/admin/expenses">报账</RouterLink>
        <RouterLink class="nav-link" to="/admin/reports">报表</RouterLink>
      </template>
    </header>
    <main class="flex-1 p-4 max-w-6xl w-full mx-auto">
      <RouterView :key="route.fullPath" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const embedded = computed(() => document.cookie.includes('ops_ui_mode=embedded'))
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header
      v-if="!embedded"
      class="bg-slate-900 text-white px-4 py-3 flex items-center justify-between shadow"
    >
      <div class="flex items-center gap-4">
        <span class="font-semibold tracking-wide">Ops Extension</span>
        <nav class="flex gap-3 text-sm">
          <RouterLink class="hover:text-sky-300" to="/tickets">我的工单</RouterLink>
          <template v-if="auth.isAdmin">
            <RouterLink class="hover:text-sky-300" to="/admin/tickets">工单管理</RouterLink>
            <RouterLink class="hover:text-sky-300" to="/admin/expenses">报账管理</RouterLink>
            <RouterLink class="hover:text-sky-300" to="/admin/suppliers">主数据</RouterLink>
            <RouterLink class="hover:text-sky-300" to="/admin/reports">费用报表</RouterLink>
          </template>
        </nav>
      </div>
      <div class="text-sm flex items-center gap-3">
        <span v-if="auth.me">{{ auth.me.username }}（{{ auth.me.sub2api_role }}）</span>
        <button
          v-if="auth.me"
          class="text-slate-300 hover:text-white"
          @click="auth.logout()"
        >
          退出
        </button>
      </div>
    </header>
    <header
      v-else
      class="bg-white border-b px-3 py-2 flex gap-3 text-sm overflow-x-auto"
    >
      <RouterLink to="/tickets">我的工单</RouterLink>
      <template v-if="auth.isAdmin">
        <RouterLink to="/admin/tickets">工单管理</RouterLink>
        <RouterLink to="/admin/expenses">报账</RouterLink>
        <RouterLink to="/admin/reports">报表</RouterLink>
      </template>
    </header>
    <main class="flex-1 p-4 max-w-6xl w-full mx-auto">
      <RouterView :key="route.fullPath" />
    </main>
  </div>
</template>

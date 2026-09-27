<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const loggedOut = computed(() => route.query.reason === 'logged_out')
const logoutFailed = computed(() => route.query.reason === 'logout_failed')
</script>
<template>
  <div class="card card-body max-w-lg mx-auto text-center">
    <h1 class="page-title mb-2">{{ loggedOut ? '已退出登录' : logoutFailed ? '退出登录未完成' : '登录失败或未授权' }}</h1>
    <p class="muted text-sm mb-4">
      {{ logoutFailed ? '请刷新页面确认登录状态。' : '请从 Sub2API 自定义菜单重新进入。' }}
      <template v-if="!loggedOut && !logoutFailed">原因：{{ route.query.reason || 'unknown' }}</template>
    </p>
  </div>
</template>

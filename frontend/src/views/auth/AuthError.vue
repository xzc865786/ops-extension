<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>
<template>
  <div class="bg-white rounded-lg shadow p-6 max-w-lg mx-auto text-center">
    <h1 class="text-xl font-semibold text-red-600 mb-2">登录失败或未授权</h1>
    <p class="text-slate-600 text-sm mb-4">
      请从 Sub2API 自定义菜单重新进入（会经过 Auth Bootstrap）。原因：{{ route.query.reason || 'unknown' }}
    </p>
  </div>
</template>

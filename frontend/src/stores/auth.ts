import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'

export interface Me {
  id: number
  sub2api_user_id: number
  username: string
  email: string
  sub2api_role: string
}

export const useAuthStore = defineStore('auth', () => {
  const me = ref<Me | null>(null)
  const loaded = ref(false)
  const isAdmin = computed(() => me.value?.sub2api_role === 'admin')

  async function fetchMe() {
    try {
      const { data } = await api.get('/auth/me')
      me.value = data
    } catch {
      me.value = null
    } finally {
      loaded.value = true
    }
  }

  async function logout() {
    try {
      await api.post('/auth/logout')
    } finally {
      me.value = null
    }
  }

  return { me, loaded, isAdmin, fetchMe, logout }
})

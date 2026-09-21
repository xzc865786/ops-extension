import { reactive } from 'vue'

export type ToastKind = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  kind: ToastKind
  message: string
}

const state = reactive<{ items: ToastItem[] }>({ items: [] })
let seq = 0

export function useToast() {
  function push(message: string, kind: ToastKind = 'info', ms = 3200) {
    const id = ++seq
    state.items.push({ id, kind, message })
    window.setTimeout(() => dismiss(id), ms)
  }

  function success(message: string) {
    push(message, 'success')
  }

  function error(message: string) {
    push(message, 'error', 4500)
  }

  function dismiss(id: number) {
    const i = state.items.findIndex((t) => t.id === id)
    if (i >= 0) state.items.splice(i, 1)
  }

  return { state, push, success, error, dismiss }
}

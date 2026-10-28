import { inject, onMounted, onUnmounted, ref, type InjectionKey } from 'vue'
import { useStorage } from './useStorage'
import { useNotifications } from './useNotifications'
import { useSession } from './useSession'
import { usePomodoro } from './usePomodoro'
import { normalizeDb } from './data'
import type { WorkItem } from './types'

export function createPdca() {
  const storage = useStorage()
  const notifications = useNotifications(storage)
  const toastText = ref('')
  const now = ref(Date.now())
  const planSelection = ref<WorkItem | null>(null)
  let toastTimeout: ReturnType<typeof setTimeout>
  function toast(text: string) {
    toastText.value = text
    clearTimeout(toastTimeout)
    toastTimeout = setTimeout(() => (toastText.value = ''), 3500)
  }
  const session = useSession(storage, notifications, toast)
  const pomodoro = usePomodoro(storage, notifications, toast)
  storage.onSaved(notifications.sync)
  let ticking = false
  async function tick() {
    now.value = Date.now()
    if (!storage.ready.value || storage.pending.value || ticking) return
    ticking = true
    try {
      await pomodoro.tick(now.value)
      session.tick(now.value)
    } finally {
      ticking = false
    }
  }
  async function load() {
    if (!(await storage.load())) return
    session.reset()
    planSelection.value = null
    await notifications.connect()
    await tick()
  }
  async function restore(value: unknown) {
    const normalized = normalizeDb(value)
    if (
      !confirm(
        '恢复备份将覆盖本机文件中的现有数据（包括正在计时的会话和番茄钟）。确定继续？',
      )
    )
      return
    storage.db.value = normalized
    session.reset()
    planSelection.value = null
    if (await storage.save()) {
      await tick()
      toast('备份恢复成功')
    }
  }
  function beforeUnload(event: BeforeUnloadEvent) {
    if (storage.dirty.value || storage.pending.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  function preventReviewEscape(event: KeyboardEvent) {
    if (session.reviewOpen.value && event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
    }
  }
  function onVisible() {
    if (!document.hidden) void tick()
  }
  let timer: ReturnType<typeof setInterval>,
    poll: ReturnType<typeof setInterval>
  onMounted(() => {
    void load()
    timer = setInterval(() => void tick(), 500)
    poll = setInterval(() => {
      if (storage.ready.value) void notifications.connect()
    }, 15000)
    window.addEventListener('beforeunload', beforeUnload)
    window.addEventListener('keydown', preventReviewEscape)
    window.addEventListener('focus', tick)
    document.addEventListener('visibilitychange', onVisible)
  })
  onUnmounted(() => {
    clearInterval(timer)
    clearInterval(poll)
    clearTimeout(toastTimeout)
    window.removeEventListener('beforeunload', beforeUnload)
    window.removeEventListener('keydown', preventReviewEscape)
    window.removeEventListener('focus', tick)
    document.removeEventListener('visibilitychange', onVisible)
  })
  return {
    storage,
    notifications,
    session,
    pomodoro,
    now,
    planSelection,
    toastText,
    toast,
    load,
    restore,
  }
}
export type Pdca = ReturnType<typeof createPdca>
export const pdcaKey: InjectionKey<Pdca> = Symbol('pdca')
export function usePdca() {
  const context = inject(pdcaKey)
  if (!context) throw new Error('PDCA context is unavailable')
  return context
}

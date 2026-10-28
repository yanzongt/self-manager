import { ref } from 'vue'
import type { Storage } from './useStorage'
import type { Notifications } from './useNotifications'
import type { Result } from './types'
import { commentsOf } from './data'
import { deadline, mins } from './time'

export function useSession(
  storage: Storage,
  notifications: Notifications,
  toast: (text: string) => void,
) {
  const reviewOpen = ref(false)
  const result = ref<Result | null>(null)
  const reviewText = ref('')
  let alerted = false
  function openReview() {
    if (!storage.db.value.active) return
    result.value = null
    reviewText.value = ''
    reviewOpen.value = true
  }
  async function start(
    purpose: string,
    tag: string,
    minutes: number,
    workItemId: string,
  ) {
    if (storage.db.value.active) return
    if (
      !purpose.trim() ||
      !tag ||
      !Number.isInteger(minutes) ||
      minutes < 1 ||
      minutes > 1440
    ) {
      toast('请填写目的、标签和1至1440分钟的预算')
      return
    }
    notifications.prepareAudio()
    const item = storage.db.value.workItems.find((w) => w.id === workItemId)
    storage.db.value.active = {
      id: crypto.randomUUID(),
      purpose: purpose.trim(),
      tag,
      budgetMinutes: minutes,
      extraMinutes: 0,
      startedAt: Date.now(),
      extensions: [],
      comments: [],
      ...(item ? { workItemId: item.id, workItemTitle: item.title } : {}),
    }
    alerted = false
    if (await storage.save()) toast('计时已开始')
  }
  function reviewData() {
    if (!result.value) {
      toast('请选择完成状态')
      return null
    }
    const note = reviewText.value.trim()
    if (!note) {
      toast('请写一点复盘内容')
      return null
    }
    return { result: result.value, note }
  }
  async function finish() {
    const review = reviewData(),
      active = storage.db.value.active
    if (!review || !active) return
    const now = Date.now()
    storage.db.value.records.push({
      id: active.id,
      startedAt: active.startedAt,
      endedAt: now,
      purpose: active.purpose,
      tag: active.tag,
      plannedMinutes: active.budgetMinutes,
      extraMinutes: active.extraMinutes,
      actualMinutes: mins(now - active.startedAt),
      result: review.result,
      review: review.note,
      extensions: active.extensions || [],
      comments: commentsOf(active),
      workItemId: active.workItemId || null,
      workItemTitle: active.workItemTitle || null,
    })
    storage.db.value.active = null
    alerted = false
    reviewOpen.value = false
    if (await storage.save()) toast('复盘已保存，闭环完成')
  }
  async function extend() {
    const review = reviewData(),
      active = storage.db.value.active
    if (!review || !active) return
    active.extensions ||= []
    active.extensions.push({
      at: Date.now(),
      actualMinutes: mins(Date.now() - active.startedAt),
      result: review.result,
      review: review.note,
      addedMinutes: 10,
    })
    active.extraMinutes = Math.max(
      active.extraMinutes + 10,
      Math.ceil((Date.now() - active.startedAt) / 60000) +
        10 -
        active.budgetMinutes,
    )
    alerted = false
    reviewOpen.value = false
    if (await storage.save()) toast('已记录阶段复盘，延长10分钟')
  }
  async function addComment(text: string) {
    const active = storage.db.value.active
    if (!active) {
      toast('请先开始一次会话')
      return false
    }
    if (!text.trim() || text.trim().length > 2000) {
      toast('评论不能为空且最多2000字符')
      return false
    }
    active.comments = [
      ...commentsOf(active),
      { id: crypto.randomUUID(), at: Date.now(), text: text.trim() },
    ]
    if (await storage.save()) {
      toast('评论和添加时间已保存')
      return true
    }
    return false
  }
  function tick(now: number) {
    const active = storage.db.value.active
    if (active && now >= deadline(active) && !alerted) {
      alerted = true
      openReview()
      if (notifications.armed.value !== `${active.id}:${deadline(active)}`)
        notifications.notify()
      notifications.beep()
    }
  }
  function reset() {
    alerted = false
    reviewOpen.value = false
  }
  return {
    reviewOpen,
    result,
    reviewText,
    openReview,
    start,
    finish,
    extend,
    addComment,
    tick,
    reset,
  }
}

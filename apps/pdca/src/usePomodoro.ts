import { computed } from 'vue'
import type { Storage } from './useStorage'
import type { Notifications } from './useNotifications'
import type { Phase, PomoSettings, Pomodoro } from './types'
import {
  advancePomodoro,
  createPomodoro,
  phaseName,
  startPomoPhase,
} from './pomodoro'

export function usePomodoro(
  storage: Storage,
  notifications: Notifications,
  toast: (text: string) => void,
) {
  const pomo = computed(() => storage.db.value.pomodoro)
  const status = computed(() =>
    !pomo.value
      ? '番茄钟已关闭'
      : pomo.value.waiting
        ? `${phaseName(pomo.value.phase)}结束，等待手动切换`
        : `正在${phaseName(pomo.value.phase)}`,
  )
  const nextLabel = computed(
    () =>
      `${pomo.value?.waiting ? '开始' : '切换到'} ${pomo.value?.phase === 'work' ? 'Break' : 'Work'}`,
  )
  function announce(timer: Pomodoro) {
    const message = `已开始${phaseName(timer.phase)}，${timer.phase === 'work' ? timer.workMinutes : timer.breakMinutes}分钟。`
    notifications.phaseEvent(
      timer,
      { at: timer.startedAt, phase: timer.phase, waiting: false, manual: true },
      `番茄钟：进入${phaseName(timer.phase)}`,
      message,
    )
    toast(message)
    notifications.beep()
  }
  async function start(phase: Phase) {
    if (pomo.value) return
    notifications.prepareAudio()
    storage.db.value.pomodoro = createPomodoro(
      Date.now(),
      storage.db.value.pomoSettings,
      phase,
    )
    announce(storage.db.value.pomodoro)
    await storage.save()
  }
  async function stop() {
    storage.db.value.pomodoro = null
    if (await storage.save()) toast('番茄钟已关闭')
  }
  async function next() {
    if (!pomo.value) return
    notifications.prepareAudio()
    startPomoPhase(
      pomo.value,
      pomo.value.phase === 'work' ? 'break' : 'work',
      Date.now(),
    )
    announce(pomo.value)
    await storage.save()
  }
  async function settings(value: PomoSettings) {
    if (
      ![value.workMinutes, value.breakMinutes].every(
        (n) => Number.isInteger(n) && n >= 1 && n <= 1440,
      )
    ) {
      toast('Work / Break 时长需为1至1440分钟的整数')
      return
    }
    storage.db.value.pomoSettings = { ...value }
    if (pomo.value) {
      pomo.value.auto = value.autoSwitch
      if (value.autoSwitch && pomo.value.waiting) {
        startPomoPhase(
          pomo.value,
          pomo.value.phase === 'work' ? 'break' : 'work',
          Date.now(),
        )
        announce(pomo.value)
      }
    }
    await storage.save()
  }
  async function tick(now: number) {
    const report = advancePomodoro(pomo.value, now)
    if (report.event && pomo.value)
      notifications.phaseEvent(
        pomo.value,
        report.event,
        report.title!,
        report.message!,
      )
    if (report.changed) await storage.save()
    if (report.message) {
      toast(report.message)
      notifications.beep()
    }
  }
  return { pomo, status, nextLabel, start, stop, next, settings, tick }
}

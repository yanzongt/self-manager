import { onUnmounted, ref } from 'vue'
import { request } from './api'
import type { Storage } from './useStorage'
import type { PhaseEvent, Pomodoro } from './types'
import { deadline } from './time'
import { nativePomodoro } from './pomodoro'

export function useNotifications(storage: Storage) {
  const nativeReady = ref(false)
  const message = ref('')
  const armed = ref<string | null>(null)
  let audio: AudioContext | null = null
  let lastNotification: Notification | null = null
  let syncQueue = Promise.resolve()
  const browserAllowed = () =>
    'Notification' in window && Notification.permission === 'granted'

  function status(text?: string) {
    message.value =
      text ||
      (nativeReady.value
        ? '系统提醒已连接；点击按钮测试。请保持本地服务运行。'
        : !('Notification' in window)
          ? '浏览器不支持桌面通知，请使用本地服务启动。'
          : browserAllowed()
            ? '浏览器通知已授权；点击按钮测试提醒。'
            : Notification.permission === 'denied'
              ? '通知已被浏览器阻止，请在地址栏的网站设置中允许通知，或使用本地启动模式。'
              : '点击开启桌面提醒并允许通知。')
  }
  function notify(
    title = '行为闭环：计划时间已到',
    body = '返回页面填写复盘，或确认延期。',
    test = false,
  ) {
    if (!browserAllowed()) return false
    try {
      lastNotification?.close()
      lastNotification = new Notification(title, {
        body,
        tag: test ? 'pdca-test' : 'pdca-time-up',
        requireInteraction: !test,
      })
      lastNotification.onclick = () => {
        window.focus()
        lastNotification?.close()
      }
      lastNotification.onerror = () =>
        status('浏览器未能显示通知，请检查系统通知设置或使用本地启动模式。')
      return true
    } catch (e) {
      status('发送通知失败：' + (e as Error).message)
      return false
    }
  }
  function prepareAudio() {
    try {
      const AC = window.AudioContext || window.webkitAudioContext
      if (!AC) return
      if (!audio || audio.state === 'closed') audio = new AC()
      if (audio.state === 'suspended')
        void audio
          .resume()
          .catch(() => status('提示音未能启用，请点击测试提醒重试。'))
    } catch (e) {
      status('无法启用提示音：' + (e as Error).message)
    }
  }
  function beep() {
    try {
      if (!audio || audio.state !== 'running') return
      for (let i = 0; i < 3; i++) {
        const oscillator = audio.createOscillator(),
          gain = audio.createGain()
        oscillator.type = 'sine'
        oscillator.frequency.value = 760
        gain.gain.value = 0.12
        oscillator.connect(gain).connect(audio.destination)
        oscillator.start(audio.currentTime + i * 0.32)
        oscillator.stop(audio.currentTime + i * 0.32 + 0.18)
        oscillator.onended = () => {
          oscillator.disconnect()
          gain.disconnect()
        }
      }
    } catch (e) {
      status('提示音播放失败：' + (e as Error).message)
    }
  }
  function sync() {
    if (!nativeReady.value) return
    const active = storage.db.value.active
    const item = active
      ? { id: active.id, deadline: deadline(active), purpose: active.purpose }
      : null
    const pomo = storage.db.value.pomodoro
    const timer = pomo
      ? {
          id: pomo.id,
          deadline: null,
          purpose: '番茄钟',
          pomodoro: nativePomodoro(pomo),
        }
      : null
    syncQueue = syncQueue
      .catch(() => {})
      .then(async () => {
        try {
          await request('/api/schedule', item)
          await request('/api/pomodoro', timer)
          armed.value = item ? `${item.id}:${item.deadline}` : null
        } catch (e) {
          armed.value = null
          status(
            '系统提醒同步失败：' + (e as Error).message + '。请检查本地服务。',
          )
        }
      })
  }
  async function connect() {
    if (!window.PDCA_NATIVE_TOKEN) {
      status()
      return
    }
    try {
      const response = await request<{ available: boolean; error?: string }>(
        '/api/status',
        undefined,
        3000,
      )
      const wasReady = nativeReady.value
      nativeReady.value = response.available
      if (!nativeReady.value) {
        armed.value = null
        status('缺少 notify-send，请安装 libnotify-bin 后重启本地服务。')
        return
      }
      if (!wasReady) {
        sync()
        status()
      }
      if (response.error) {
        armed.value = null
        status('系统提醒失败：' + response.error + '。请点击按钮重试。')
      }
    } catch {
      nativeReady.value = false
      armed.value = null
      status('本地服务已断开，请重新运行 ./start.sh。')
    }
  }
  function phaseEvent(
    pomo: Pomodoro,
    event: PhaseEvent,
    title: string,
    body: string,
  ) {
    if (nativeReady.value) {
      void request('/api/phase', {
        ...event,
        id: pomo.id,
        purpose: '番茄钟',
      }).catch((e) => {
        status('番茄钟系统提醒失败：' + (e as Error).message)
        notify(title, body)
      })
    } else notify(title, body)
  }
  async function test() {
    prepareAudio()
    if (nativeReady.value) {
      try {
        await request('/api/test', {})
        status('测试提醒已交给系统；若未显示，请检查系统通知设置。')
        beep()
      } catch (e) {
        status('系统通知失败：' + (e as Error).message)
      }
      return
    }
    if (!('Notification' in window) || Notification.permission === 'denied') {
      status()
      return
    }
    if (!window.isSecureContext) {
      status('通知需要安全地址，请使用本地服务并访问本机地址。')
      return
    }
    try {
      const permission = browserAllowed()
        ? 'granted'
        : await Notification.requestPermission()
      status()
      if (permission === 'granted') {
        notify(
          '行为闭环：测试提醒',
          '桌面提醒已发送。若没有看到，请检查系统勿扰和通知设置。',
          true,
        )
        beep()
      }
    } catch (e) {
      status('无法请求通知权限：' + (e as Error).message)
    }
  }
  onUnmounted(() => {
    lastNotification?.close()
    void audio?.close()
  })
  status()
  return {
    nativeReady,
    message,
    armed,
    browserAllowed,
    prepareAudio,
    beep,
    notify,
    sync,
    connect,
    phaseEvent,
    test,
  }
}
export type Notifications = ReturnType<typeof useNotifications>

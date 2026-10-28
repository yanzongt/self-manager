import type { Phase, PhaseEvent, PomoSettings, Pomodoro } from './types'
export const phaseName = (phase: Phase) =>
  phase === 'work' ? 'Work · 专注' : 'Break · 休息'
export function startPomoPhase(pomo: Pomodoro, phase: Phase, at: number) {
  pomo.phase = phase
  pomo.startedAt = at
  pomo.phaseEndsAt =
    at + (phase === 'work' ? pomo.workMinutes : pomo.breakMinutes) * 60000
  pomo.waiting = false
  pomo.stopped = false
}
export function createPomodoro(
  at: number,
  settings: PomoSettings,
  phase: Phase,
): Pomodoro {
  return {
    id: crypto.randomUUID(),
    phase,
    startedAt: at,
    phaseEndsAt:
      at +
      (phase === 'work' ? settings.workMinutes : settings.breakMinutes) * 60000,
    workMinutes: settings.workMinutes,
    breakMinutes: settings.breakMinutes,
    auto: settings.autoSwitch,
    waiting: false,
    stopped: false,
  }
}
export function nativePomodoro(p: Pomodoro) {
  return {
    phase: p.phase,
    startedAt: p.startedAt,
    phaseEndsAt: p.phaseEndsAt,
    workMinutes: p.workMinutes,
    breakMinutes: p.breakMinutes,
    auto: p.auto,
    waiting: p.waiting,
    stopped: p.stopped,
  }
}
export function advancePomodoro(pomo: Pomodoro | null, now: number) {
  const report: {
    changed: boolean
    message?: string
    title?: string
    event?: PhaseEvent
  } = { changed: false }
  if (!pomo || pomo.stopped || pomo.waiting || now < pomo.phaseEndsAt)
    return report
  // Skip full cycles after a long sleep; do not replay every missed notification.
  const cycle = (pomo.workMinutes + pomo.breakMinutes) * 60000
  let switches = 0
  if (pomo.auto && now - pomo.phaseEndsAt >= cycle) {
    const cycles = Math.floor((now - pomo.phaseEndsAt) / cycle)
    pomo.startedAt += cycles * cycle
    pomo.phaseEndsAt += cycles * cycle
    switches += cycles * 2
  }
  while (!pomo.waiting && pomo.phaseEndsAt <= now) {
    const end = pomo.phaseEndsAt
    const previous = pomo.phase
    report.changed = true
    if (!pomo.auto) {
      pomo.waiting = true
      report.event = { at: end, phase: previous, waiting: true, manual: false }
      report.title = '番茄钟：阶段结束'
      report.message = `${phaseName(previous)}结束，请手动开始${phaseName(previous === 'work' ? 'break' : 'work')}。`
      break
    }
    startPomoPhase(pomo, previous === 'work' ? 'break' : 'work', end)
    switches++
    report.event = {
      at: end,
      phase: pomo.phase,
      waiting: false,
      manual: false,
    }
    report.title = `番茄钟：进入${phaseName(pomo.phase)}`
    report.message = `已切换到${phaseName(pomo.phase)}，${pomo.phase === 'work' ? pomo.workMinutes : pomo.breakMinutes}分钟。`
  }
  if (switches > 1)
    report.message = `已按时间恢复 ${switches} 次阶段切换；当前${phaseName(pomo.phase)}。`
  return report
}

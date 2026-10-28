import { describe, expect, it } from 'vitest'
import { advancePomodoro, createPomodoro } from './pomodoro'
import { normalizeDb, defaults } from './data'
import { dailyMinutes, dateSeries } from './analytics'
const settings = { workMinutes: 25, breakMinutes: 5, autoSwitch: true }
describe('independent pomodoro', () => {
  it('starts with Break, catches up across multiple phases and emits only the final event', () => {
    const timer = createPomodoro(0, settings, 'break')
    const report = advancePomodoro(timer, 65 * 60000)
    expect(timer.phase).toBe('work')
    expect(timer.startedAt).toBe(65 * 60000)
    expect(timer.phaseEndsAt).toBe(90 * 60000)
    expect(report.event).toEqual({
      at: 65 * 60000,
      phase: 'work',
      waiting: false,
      manual: false,
    })
    expect(report.message).toContain('5 次阶段切换')
    expect(advancePomodoro(timer, 65 * 60000).changed).toBe(false)
  })
  it('waits at the boundary in manual mode and never appends phase history', () => {
    const timer = createPomodoro(0, { ...settings, autoSwitch: false }, 'work')
    expect(advancePomodoro(timer, 25 * 60000).event?.waiting).toBe(true)
    expect(timer.waiting).toBe(true)
    expect(timer.phase).toBe('work')
    expect(advancePomodoro(timer, 60 * 60000).changed).toBe(false)
    expect(timer.records).toBeUndefined()
  })
  it('restores years of missed cycles without iterating every phase', () => {
    const timer = createPomodoro(0, settings, 'work')
    const now = 10 * 365 * 24 * 60 * 60000
    expect(advancePomodoro(timer, now).changed).toBe(true)
    expect(timer.startedAt).toBeLessThanOrEqual(now)
    expect(timer.phaseEndsAt).toBeGreaterThan(now)
  })
})
describe('legacy compatibility and daily statistics', () => {
  it('migrates an active session timer without losing its legacy history', () => {
    const timer = {
      ...createPomodoro(0, settings, 'work'),
      records: [{ phase: 'work' as const, startedAt: 0, endedAt: 1000 }],
    }
    const data = normalizeDb({
      tags: ['工作'],
      records: [],
      active: {
        id: 's',
        purpose: '旧会话',
        tag: '工作',
        startedAt: 0,
        budgetMinutes: 30,
        extraMinutes: 0,
        pomodoro: timer,
      },
    })
    expect(data.pomodoro?.id).toBe(timer.id)
    expect(data.active?.pomodoro?.records).toEqual(timer.records)
    expect(data.utilizationHours).toBe(8)
    expect(data.workItems).toEqual([])
    expect(normalizeDb({ ...data, pomodoro: null }).pomodoro).toBeNull()
  })
  it('counts all completed reviews by local start date and fills missing days', () => {
    const data = defaults(),
      at = new Date(2026, 9, 28, 12).getTime()
    data.records = [
      {
        id: 'r',
        purpose: '阅读',
        tag: '学习',
        startedAt: at,
        endedAt: at + 60000,
        actualMinutes: 600,
        plannedMinutes: 30,
        extraMinutes: 0,
        result: 'partial',
        review: '继续',
      },
    ]
    const points = dateSeries(dailyMinutes(data.records), 3, at)
    expect(points.map((p) => p.value)).toEqual([0, 0, 600])
    expect((points[2].value / (data.utilizationHours * 60)) * 100).toBe(125)
  })
})

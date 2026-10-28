import { nativePomodoro } from './pomodoro'
import type {
  Comment,
  Database,
  PomoSettings,
  Pomodoro,
  HistoryRecord,
  WorkItem,
  ActiveSession,
} from './types'

export const LEGACY_KEY = 'focus_pdca_singlefile_v1'
export function defaults(): Database {
  return {
    tags: ['学习', '工作', '娱乐', '运动', '阅读', '其他'],
    records: [],
    active: null,
    workItems: [],
    utilizationHours: 8,
    pomoSettings: { workMinutes: 25, breakMinutes: 5, autoSwitch: true },
    pomodoro: null,
  }
}
function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {}
}
function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}
export function normalizePomoSettings(value: unknown): PomoSettings {
  const settings = object(value)
  const minutes = (v: unknown, fallback: number) =>
    finite(v) && Number.isInteger(v) && v >= 1 && v <= 1440 ? v : fallback
  return {
    workMinutes: minutes(settings.workMinutes, 25),
    breakMinutes: minutes(settings.breakMinutes, 5),
    autoSwitch:
      typeof settings.autoSwitch === 'boolean' ? settings.autoSwitch : true,
  }
}
export function normalizePomodoro(value: unknown): Pomodoro | null {
  const p = object(value)
  if (
    !['work', 'break'].includes(String(p.phase)) ||
    !finite(p.startedAt) ||
    !finite(p.phaseEndsAt) ||
    p.phaseEndsAt <= p.startedAt
  )
    return null
  const settings = normalizePomoSettings(p)
  return {
    ...p,
    id: typeof p.id === 'string' ? p.id : crypto.randomUUID(),
    phase: p.phase as Pomodoro['phase'],
    startedAt: p.startedAt,
    phaseEndsAt: p.phaseEndsAt,
    workMinutes: settings.workMinutes,
    breakMinutes: settings.breakMinutes,
    auto: p.auto === true,
    waiting: p.waiting === true,
    stopped: p.stopped === true,
    records: Array.isArray(p.records)
      ? p.records.filter((record) => {
          const r = object(record)
          return (
            ['work', 'break'].includes(String(r.phase)) &&
            finite(r.startedAt) &&
            finite(r.endedAt) &&
            r.endedAt >= r.startedAt
          )
        })
      : [],
  }
}
export function normalizeDb(value: unknown): Database {
  const data = object(value)
  if (
    !Array.isArray(data.tags) ||
    !data.tags.length ||
    !data.tags.every((tag) => typeof tag === 'string') ||
    !Array.isArray(data.records)
  )
    throw new Error('结构不正确')
  const validSession = (session: unknown) => {
    const s = object(session)
    return (
      typeof s.id === 'string' &&
      typeof s.purpose === 'string' &&
      typeof s.tag === 'string' &&
      finite(s.startedAt)
    )
  }
  if (
    !data.records.every(validSession) ||
    (data.active != null && !validSession(data.active))
  )
    throw new Error('无效会话记录')
  const active = data.active ? object(data.active) : null
  const independent = normalizePomodoro(
    Object.hasOwn(data, 'pomodoro') ? data.pomodoro : active?.pomodoro,
  )
  const hours = data.utilizationHours
  return {
    ...defaults(),
    ...data,
    tags: data.tags,
    utilizationHours: finite(hours) && hours >= 0.1 && hours <= 24 ? hours : 8,
    workItems: (Array.isArray(data.workItems)
      ? data.workItems.filter((value) => {
          const w = object(value)
          return (
            typeof w.id === 'string' &&
            typeof w.title === 'string' &&
            typeof w.important === 'boolean' &&
            typeof w.urgent === 'boolean'
          )
        })
      : []) as WorkItem[],
    pomoSettings: normalizePomoSettings(data.pomoSettings),
    pomodoro:
      independent && !independent.stopped
        ? { id: independent.id, ...nativePomodoro(independent) }
        : null,
    active: active
      ? ({
          ...active,
          extraMinutes: active.extraMinutes || 0,
          pomodoro: normalizePomodoro(active.pomodoro),
        } as unknown as ActiveSession)
      : null,
    records: data.records.map((value) => {
      const r = object(value)
      return {
        ...r,
        pomodoro: normalizePomodoro(r.pomodoro),
      } as unknown as HistoryRecord
    }),
  }
}
export function legacyData(): Database | null {
  try {
    const raw = localStorage.getItem(LEGACY_KEY)
    return raw ? normalizeDb(JSON.parse(raw)) : null
  } catch {
    return null
  }
}
export const commentsOf = (session: { comments?: Comment[] } | null) =>
  Array.isArray(session?.comments)
    ? session.comments.filter(
        (c) =>
          c &&
          typeof c.id === 'string' &&
          typeof c.text === 'string' &&
          finite(c.at) &&
          Number.isFinite(new Date(c.at).getTime()),
      )
    : []

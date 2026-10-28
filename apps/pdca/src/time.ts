import type { ActiveSession, HistoryRecord } from './types'
const pad = (value: number) => String(value).padStart(2, '0')
export function day(time: number | Date) {
  const date = new Date(time)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}
export function fmt(time: number) {
  const date = new Date(time)
  return `${day(time)} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
export const fmtComment = (time: number) =>
  `${fmt(time)}:${pad(new Date(time).getSeconds())}`
export const mins = (ms: number) =>
  Math.round((Math.max(0, ms) / 60000) * 10) / 10
export const formatMin = (minutes: number) =>
  String(Math.round(minutes * 10) / 10)
export function clock(ms: number) {
  const seconds = Math.ceil(Math.abs(ms) / 1000)
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor((seconds % 3600) / 60))}:${pad(seconds % 60)}`
}
export const currentTotal = (session: ActiveSession) =>
  session.budgetMinutes + (session.extraMinutes || 0)
export const deadline = (session: ActiveSession) =>
  session.startedAt + currentTotal(session) * 60000

export const duration = (record: HistoryRecord) =>
  Number(record.actualMinutes) || 0

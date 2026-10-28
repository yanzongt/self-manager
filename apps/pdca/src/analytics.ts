import type { HistoryRecord } from './types'
import { day, duration } from './time'
export function dailyMinutes(records: HistoryRecord[]) {
  const totals = new Map<string, number>()
  for (const record of records) {
    const minutes = duration(record),
      date = day(record.startedAt)
    if (Number.isFinite(minutes) && minutes >= 0)
      totals.set(date, (totals.get(date) || 0) + minutes)
  }
  return totals
}
export function dateSeries(
  totals: Map<string, number>,
  range: number | 'all',
  now: number,
) {
  const today = new Date(now)
  today.setHours(0, 0, 0, 0)
  const start = new Date(today)
  if (range === 'all') {
    const first = [...totals.keys()]
      .filter((date) => date <= day(today))
      .sort()[0]
    if (first) start.setTime(new Date(first + 'T00:00:00').getTime())
  } else start.setDate(start.getDate() - range + 1)
  const points: { label: string; value: number }[] = []
  for (
    const date = new Date(start);
    date <= today;
    date.setDate(date.getDate() + 1)
  ) {
    const label = day(date)
    points.push({ label, value: totals.get(label) || 0 })
  }
  return points
}

import type { Comment, Database, HistoryRecord, Session } from './types'
import { commentsOf } from './data'
import { day, fmt, fmtComment, formatMin, duration } from './time'
export const resultLabels = {
  completed: '已完成',
  partial: '部分完成',
  not_completed: '未完成',
}
export function download(
  text: string,
  name: string,
  type = 'text/plain;charset=utf-8',
) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
const suffix = (id: string) => id.replace(/[^a-zA-Z0-9_-]/g, '').slice(-8)
const commentsText = (session: Session) =>
  commentsOf(session)
    .map((c, i) => `评论${i + 1}（${fmtComment(c.at)}）：${c.text}\n`)
    .join('')
export function exportComment(session: Session, comment: Comment) {
  const text = `行为闭环 · 单条评论\n项目：${session.tag}\n目的：${session.purpose}\n会话开始：${fmtComment(session.startedAt)}\n评论添加时间：${fmtComment(comment.at)}\n时间戳（UTC）：${new Date(comment.at).toISOString()}\n\n${comment.text}\n`
  download(
    text,
    `行为闭环_评论_${day(comment.at)}_${comment.at}_${suffix(comment.id)}.txt`,
  )
}
export function recordText(record: HistoryRecord) {
  let text = `开始时间：${fmtComment(record.startedAt)}\n结束时间：${fmtComment(record.endedAt)}\n项目：${record.tag}\n目的：${record.purpose}\n计划时长：${record.plannedMinutes} 分钟\n延长时长：${record.extraMinutes || 0} 分钟\n实际时长：${formatMin(duration(record))} 分钟\n结果：${resultLabels[record.result] || '未知'}\n复盘：${record.review}\n`
  for (const [i, extension] of (record.extensions || []).entries())
    text += `阶段复盘${i + 1}（${fmtComment(extension.at)}，+${extension.addedMinutes}分钟）：${extension.review}\n`
  return (
    text +
    commentsText(record) +
    (record.workItemTitle ? `Work item：${record.workItemTitle}\n` : '')
  )
}
export function exportRecord(record: HistoryRecord) {
  download(
    `行为闭环 · 单条历史记录\n导出时间：${fmtComment(Date.now())}\n\n${recordText(record)}`,
    `行为闭环_记录_${day(record.startedAt)}_${record.startedAt}_${suffix(record.id)}.txt`,
  )
}
export function exportTxt(db: Database) {
  const rows = [...db.records].sort((a, b) => a.startedAt - b.startedAt)
  let text = `个人行为闭环记录\n导出时间：${fmt(Date.now())}\n会话数：${rows.length}\n累计时长：${formatMin(rows.reduce((sum, r) => sum + duration(r), 0))} 分钟\n\n`
  for (const [i, record] of rows.entries())
    text += `【${i + 1}】\n${recordText(record)}\n`
  if (db.active)
    text += `【进行中的会话，尚未复盘】\n${fmt(db.active.startedAt)} / ${db.active.tag} / ${db.active.purpose}\n${commentsText(db.active)}`
  download(text, `行为闭环_${day(Date.now())}.txt`)
}
export function exportJson(db: Database, legacy = false) {
  download(
    JSON.stringify(
      { version: 1, exportedAt: new Date().toISOString(), data: db },
      null,
      2,
    ),
    `行为闭环_${legacy ? '旧浏览器备份' : '备份'}_${day(Date.now())}.json`,
    'application/json',
  )
}

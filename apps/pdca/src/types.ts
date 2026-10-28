export type Phase = 'work' | 'break'
export type Result = 'completed' | 'partial' | 'not_completed'
export interface Comment {
  id: string
  at: number
  text: string
}
export interface Extension {
  at: number
  actualMinutes: number
  result: Result
  review: string
  addedMinutes: number
}
export interface PomoSettings {
  workMinutes: number
  breakMinutes: number
  autoSwitch: boolean
}
export interface PomoStage {
  phase: Phase
  startedAt: number
  endedAt: number
}
export interface Pomodoro {
  id: string
  phase: Phase
  startedAt: number
  phaseEndsAt: number
  workMinutes: number
  breakMinutes: number
  auto: boolean
  waiting: boolean
  stopped: boolean
  records?: PomoStage[]
}
export interface Session {
  id: string
  startedAt: number
  purpose: string
  tag: string
  comments?: Comment[]
  extensions?: Extension[]
  workItemId?: string | null
  workItemTitle?: string | null
  pomodoro?: Pomodoro | null
}
export interface ActiveSession extends Session {
  budgetMinutes: number
  extraMinutes: number
}
export interface HistoryRecord extends Session {
  endedAt: number
  plannedMinutes: number
  extraMinutes: number
  actualMinutes: number
  result: Result
  review: string
}
export interface WorkItem {
  id: string
  title: string
  important: boolean
  urgent: boolean
  done: boolean
  createdAt: number
  updatedAt?: number
  completedAt?: number | null
}
export interface Database {
  tags: string[]
  records: HistoryRecord[]
  active: ActiveSession | null
  workItems: WorkItem[]
  utilizationHours: number
  pomoSettings: PomoSettings
  pomodoro: Pomodoro | null
}
export interface PhaseEvent {
  at: number
  phase: Phase
  waiting: boolean
  manual: boolean
}

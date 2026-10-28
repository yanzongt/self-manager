<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePdca } from '../usePdca'
import { dailyMinutes, dateSeries } from '../analytics'
import { day, formatMin, duration } from '../time'
import LineChart from './LineChart.vue'
const { storage, now, toast } = usePdca()
const { db } = storage
const period = ref('all'),
  trendTag = ref('all'),
  range = ref<number | 'all'>(30)
const todayRecords = computed(() =>
  db.value.records.filter((r) => day(r.startedAt) === day(now.value)),
)
const total = (records: typeof db.value.records) =>
  records.reduce((sum, r) => sum + duration(r), 0)
const rate = computed(() =>
  db.value.records.length
    ? Math.round(
        (db.value.records.filter((r) => r.result === 'completed').length /
          db.value.records.length) *
          100,
      ) + '%'
    : '—',
)
const bars = computed(() => {
  const floor = new Date(now.value)
  floor.setHours(0, 0, 0, 0)
  if (period.value === 'week') floor.setDate(floor.getDate() - 6)
  const totals = new Map<string, number>()
  for (const record of db.value.records)
    if (period.value === 'all' || record.startedAt >= floor.getTime())
      totals.set(record.tag, (totals.get(record.tag) || 0) + duration(record))
  return [...totals].sort((a, b) => b[1] - a[1]).slice(0, 7)
})
const barMax = computed(() => Math.max(1, ...bars.value.map(([, v]) => v)))
const trend = computed(() => {
  const records = db.value.records.filter(
    (r) => trendTag.value === 'all' || r.tag === trendTag.value,
  )
  if (!records.length) return []
  const totals = dailyMinutes(records)
  const first = [...totals.keys()].sort()[0]
  const end = new Date(now.value)
  end.setHours(0, 0, 0, 0)
  const span = Math.max(
    1,
    Math.min(
      30,
      Math.round(
        (end.getTime() - new Date(first + 'T00:00:00').getTime()) / 86400000,
      ) + 1,
    ),
  )
  return dateSeries(totals, span, now.value)
})
const utilization = computed(() =>
  dateSeries(dailyMinutes(db.value.records), range.value, now.value).map(
    (point) => ({
      label: point.label,
      minutes: point.value,
      value: (point.value / (db.value.utilizationHours * 60)) * 100,
      detail: `${point.label}：已记录 ${formatMin(point.value / 60)} 小时 / 目标 ${db.value.utilizationHours} 小时，利用率 ${formatMin((point.value / (db.value.utilizationHours * 60)) * 100)}%`,
    }),
  ),
)
const todayMinutes = computed(() => total(todayRecords.value))
const average = computed(
  () =>
    utilization.value.reduce((sum, point) => sum + point.value, 0) /
    utilization.value.length,
)
async function setHours(event: Event) {
  const input = event.target as HTMLInputElement,
    value = Number(input.value)
  if (!Number.isFinite(value) || value < 0.1 || value > 24) {
    input.value = String(db.value.utilizationHours)
    toast('每日目标时长需为 0.1 至 24 小时')
    return
  }
  db.value.utilizationHours = value
  if (await storage.save()) toast('每日目标时长已保存，利用率已重新计算')
}
</script>
<template>
  <div class="summary">
    <div class="stat">
      <div class="name">今日总耗时</div>
      <div id="todayStat" class="value">
        {{ formatMin(todayMinutes) }}
        <small style="font-size: 12px">分钟</small>
      </div>
      <div id="todayCount" class="sub">
        {{ todayRecords.length }} 次已完成复盘
      </div>
    </div>
    <div class="stat">
      <div class="name">累计总耗时</div>
      <div id="allStat" class="value">
        {{ formatMin(total(db.records)) }}
        <small style="font-size: 12px">分钟</small>
      </div>
      <div id="allCount" class="sub">{{ db.records.length }} 次已复盘会话</div>
    </div>
    <div class="stat">
      <div class="name">目标完成率</div>
      <div id="rateStat" class="value">{{ rate }}</div>
      <div class="sub">仅统计已复盘会话</div>
    </div>
  </div>
  <div class="viz-grid">
    <section class="sm-panel panel chart-panel">
      <div class="chart-title">
        <h2>项目耗时分布</h2>
        <select
          id="periodFilter"
          v-model="period"
          class="sm-control control chart-filter"
        >
          <option value="all">全部时间</option>
          <option value="today">仅今天</option>
          <option value="week">最近7天</option>
        </select>
      </div>
      <div id="tagChart" class="chart">
        <div v-if="!bars.length" class="empty">该时间范围暂无数据</div>
        <svg
          v-else
          :viewBox="`0 0 350 ${Math.max(205, bars.length * 29 + 12)}`"
          preserveAspectRatio="xMinYMin meet"
          role="img"
          aria-label="各项目累计使用分钟数"
        >
          <template v-for="([tag, value], index) in bars" :key="tag">
            <text x="0" :y="20 + index * 29">
              {{ tag.length > 7 ? tag.slice(0, 7) + '…' : tag }}
            </text>
            <rect
              x="93"
              :y="8 + index * 29"
              width="195"
              height="15"
              rx="5"
              fill="var(--sm-surface-muted)"
            />
            <rect
              x="93"
              :y="8 + index * 29"
              :width="(195 * value) / barMax"
              height="15"
              rx="5"
              fill="var(--sm-chart)"
            />
            <text x="296" :y="20 + index * 29">{{ formatMin(value) }}m</text>
          </template>
        </svg>
      </div>
    </section>
    <section class="sm-panel panel chart-panel">
      <div class="chart-title">
        <h2>历史耗时趋势</h2>
        <select
          id="trendTag"
          v-model="trendTag"
          class="sm-control control chart-filter"
        >
          <option value="all">全部项目</option>
          <option v-for="tag in db.tags" :key="tag" :value="tag">
            {{ tag }}
          </option>
        </select>
      </div>
      <div id="trendChart" class="chart">
        <LineChart
          v-if="trend.length"
          :points="trend"
          label="最近最多30天按日期的使用时间折线图"
        />
        <div v-else class="empty">该项目暂无历史数据</div>
      </div>
    </section>
  </div>
  <section
    class="sm-panel panel chart-panel utilization-panel"
    aria-labelledby="utilizationTitle"
  >
    <div class="chart-title utilization-heading">
      <h2 id="utilizationTitle">每日时间利用率</h2>
      <div class="utilization-controls">
        <label for="utilizationHours">
          每日目标（小时）
          <input
            id="utilizationHours"
            class="sm-control control"
            type="number"
            min="0.1"
            max="24"
            step="any"
            :value="db.utilizationHours"
            @change="setHours"
          />
        </label>
        <label for="utilizationRange">
          查看范围
          <select
            id="utilizationRange"
            v-model="range"
            class="sm-control control"
          >
            <option :value="7">最近7天</option>
            <option :value="30">最近30天</option>
            <option :value="90">最近90天</option>
            <option value="all">全部记录至今</option>
          </select>
        </label>
      </div>
    </div>
    <p id="utilizationSummary" class="muted" role="status" aria-live="polite">
      今日 {{ formatMin((todayMinutes / (db.utilizationHours * 60)) * 100) }}% ·
      已记录 {{ formatMin(todayMinutes / 60) }} /
      {{ db.utilizationHours }} 小时；图示 {{ utilization.length }} 天平均
      {{ formatMin(average) }}%（含未记录日）。
    </p>
    <div id="utilizationChart" class="utilization-chart">
      <LineChart
        :points="utilization"
        percent
        :label="`每日时间利用率折线图，目标每天 ${db.utilizationHours} 小时`"
      />
    </div>
    <p class="hint">
      利用率 = 当天已记录的实际时长 ÷
      每日目标时长。汇总全部标签的已复盘会话，按开始日期归属；未记录的日期按 0%
      计，超过目标可高于
      100%。修改目标后，整条曲线按新目标重新计算。悬停或聚焦数据点可查看当日详情。
    </p>
  </section>
</template>

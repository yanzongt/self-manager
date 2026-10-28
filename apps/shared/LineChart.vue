<script setup lang="ts">
import { computed, ref, watch } from "vue";
const props = defineProps<{
  series: {
    name: string;
    color?: string;
    points: { date: string; value: number }[];
  }[];
  label: string;
  percent?: boolean;
}>();
const active = ref<number | null>(null);
const showData = ref(false);
const points = computed(() =>
  props.series.flatMap((s) => s.points).filter((p) => Number.isFinite(p.value)),
);
const dates = computed(() =>
  [...new Set(points.value.map((p) => p.date))].sort(),
);
const bounds = computed(() => {
  const values = points.value.map((p) => p.value);
  const min = values.reduce((a, v) => Math.min(a, v), 0),
    max = values.reduce((a, v) => Math.max(a, v), 0);
  return { min, max: max === min ? min + 1 : max };
});
const dateIndices = computed(
  () => new Map(dates.value.map((date, i) => [date, i])),
);
watch(dates, () => {
  active.value = null;
});
const x = (date: string) =>
  60 +
  ((dateIndices.value.get(date) ?? 0) * 810) /
    Math.max(1, dates.value.length - 1);
const y = (value: number) =>
  240 -
  ((value - bounds.value.min) / (bounds.value.max - bounds.value.min)) * 210;
const renderedSeries = computed(() =>
  props.series.map((s) => ({
    ...s,
    path: s.points.map((p) => `${x(p.date)},${y(p.value)}`).join(" "),
  })),
);
function inspect(event: PointerEvent) {
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
  const fraction =
    (((event.clientX - rect.left) * 900) / rect.width - 60) / 810;
  active.value = Math.max(
    0,
    Math.min(
      dates.value.length - 1,
      Math.round(fraction * (dates.value.length - 1)),
    ),
  );
}
const format = (value: number) =>
  !Number.isFinite(value)
    ? "—"
    : props.percent
      ? `${(value * 100).toFixed(1)}%`
      : value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
</script>
<template>
  <div class="sm-line-chart">
    <p v-if="!points.length" class="chart-empty">
      暂无数据，添加记录后查看趋势。
    </p>
    <svg
      v-else
      viewBox="0 0 900 280"
      role="img"
      :aria-label="label"
      @pointerleave="active = null"
      @pointermove="inspect"
    >
      <title>{{ label }}</title>
      <g v-for="i in 5" :key="i">
        <line
          x1="60"
          x2="870"
          :y1="30 + (i - 1) * 52.5"
          :y2="30 + (i - 1) * 52.5"
          stroke="var(--sm-border)"
        />
        <text x="50" :y="34 + (i - 1) * 52.5" text-anchor="end">
          {{ format(bounds.max - ((bounds.max - bounds.min) * (i - 1)) / 4) }}
        </text>
      </g>
      <g
        v-for="s in renderedSeries"
        :key="s.name"
        :style="{ color: s.color || 'var(--sm-chart)' }"
      >
        <polyline
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          :points="s.path"
        />
        <circle
          v-if="s.points.length === 1"
          :cx="x(s.points[0].date)"
          :cy="y(s.points[0].value)"
          r="4"
          fill="currentColor"
        />
      </g>
      <text
        v-for="i in [
          ...new Set([0, Math.floor((dates.length - 1) / 2), dates.length - 1]),
        ]"
        :key="i"
        :x="x(dates[i])"
        y="267"
        text-anchor="middle"
      >
        {{ dates[i]?.slice(0, 10) }}
      </text>
      <rect x="60" y="20" width="810" height="225" fill="transparent" />
      <line
        v-if="active !== null"
        :x1="x(dates[active])"
        :x2="x(dates[active])"
        y1="20"
        y2="240"
        stroke="var(--sm-muted)"
        stroke-dasharray="4"
      />
    </svg>
    <div v-if="active !== null" role="status">
      {{ dates[active] }}
      <span v-for="s in series" :key="s.name">
        · {{ s.name }}
        {{
          format(
            s.points.find((p) => p.date === dates[active ?? 0])?.value ?? NaN,
          )
        }}</span
      >
    </div>
    <details
      v-if="points.length"
      @toggle="showData = ($event.target as HTMLDetailsElement).open"
    >
      <summary>查看图表数据</summary>
      <div v-if="showData" class="chart-data">
        <p v-if="series.some((s) => s.points.length > 500)">
          每个系列显示最近 500 条。
        </p>
        <table>
          <thead>
            <tr>
              <th>系列</th>
              <th>日期</th>
              <th>数值</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="s in series" :key="s.name"
              ><tr v-for="p in s.points.slice(-500)" :key="p.date">
                <td>{{ s.name }}</td>
                <td>{{ p.date }}</td>
                <td>{{ format(p.value) }}</td>
              </tr></template
            >
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>
<style scoped>
.sm-line-chart {
  min-width: 0;
}
svg {
  display: block;
  width: 100%;
  height: auto;
  min-height: 150px;
}
text {
  font: 11px var(--sm-font);
  fill: var(--sm-muted);
}
.chart-empty {
  text-align: center;
  padding: 64px 12px;
  color: var(--sm-muted);
}
summary {
  font-size: 12px;
  color: var(--sm-muted);
  cursor: pointer;
}
.chart-data {
  max-height: 240px;
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
}
td,
th {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid var(--sm-border);
}
</style>

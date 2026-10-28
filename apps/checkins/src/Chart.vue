<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{
  days: string[];
  values: Record<string, number>;
  unit: string;
  color: string;
}>();
const max = computed(() =>
  Math.max(1, ...props.days.map((d) => props.values[d] || 0)),
);
const step = computed(() => 464 / props.days.length);
const bw = computed(() => Math.min(32, step.value * 0.6));
</script>
<template>
  <svg
    class="chart"
    viewBox="0 0 520 230"
    role="img"
    :aria-label="`最近 ${days.length} 天每日${unit === '次' ? '打卡次数' : '打卡时长'}`"
  >
    <title>
      每日统计：{{
        days
          .map(
            (d) =>
              d + " " + (values[d] || 0).toFixed(unit === "次" ? 0 : 1) + unit,
          )
          .join("，")
      }}
    </title>
    <template v-for="n in 5" :key="n">
      <line
        x1="44"
        :y1="194 - (171 * (n - 1)) / 4"
        x2="510"
        :y2="194 - (171 * (n - 1)) / 4"
        stroke="#e8e9df"
      />
      <text x="36" :y="198 - (171 * (n - 1)) / 4" text-anchor="end">
        {{ +((max * (n - 1)) / 4).toFixed(1) }}
      </text>
    </template>
    <template v-for="(d, i) in days" :key="d">
      <rect
        :x="44 + step * (i + 0.5) - bw / 2"
        :y="194 - (171 * (values[d] || 0)) / max"
        :width="bw"
        :height="(171 * (values[d] || 0)) / max"
        rx="3"
        :fill="color"
      >
        <title>{{ d }}：{{ +(values[d] || 0).toFixed(2) }} {{ unit }}</title>
      </rect>
      <text
        v-if="days.length === 7 || i % 5 === 0 || i === days.length - 1"
        :x="44 + step * (i + 0.5)"
        y="216"
        text-anchor="middle"
      >
        {{ d.slice(5).replace("-", "/") }}
      </text>
      <text
        v-if="values[d] && days.length === 7"
        :x="44 + step * (i + 0.5)"
        :y="187 - (171 * (values[d] || 0)) / max"
        text-anchor="middle"
      >
        {{ +(values[d] || 0).toFixed(1) }}
      </text>
    </template>
    <text
      v-if="!days.some((d) => values[d])"
      x="280"
      y="95"
      text-anchor="middle"
    >
      这段时间还没有记录
    </text>
  </svg>
</template>

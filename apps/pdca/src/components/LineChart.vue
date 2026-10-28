<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { formatMin } from '../time'
const props = defineProps<{
  points: { label: string; value: number; detail?: string }[]
  percent?: boolean
  label: string
}>()
const svg = ref<SVGSVGElement | null>(null)
const width = ref(720)
let observer: ResizeObserver | undefined
onMounted(() => {
  const host = svg.value?.parentElement
  if (!host) return
  const resize = () => {
    width.value = Math.max(320, host.clientWidth)
  }
  resize()
  observer = new ResizeObserver(resize)
  observer.observe(host)
})
onUnmounted(() => observer?.disconnect())
const max = computed(() =>
  props.percent
    ? Math.max(
        100,
        Math.ceil(Math.max(0, ...props.points.map((p) => p.value)) / 25) * 25,
      )
    : Math.max(1, ...props.points.map((p) => p.value)),
)
const x = (index: number) =>
  52 +
  (width.value - 76) *
    (props.points.length === 1 ? 0.5 : index / (props.points.length - 1))
const y = (value: number) => 190 - (168 * value) / max.value
const ticks = computed(() =>
  [
    ...new Set([
      0,
      Math.floor((props.points.length - 1) / 2),
      props.points.length - 1,
    ]),
  ].filter((i) => i >= 0),
)
const polyline = computed(() =>
  props.points.map((point, i) => `${x(i)},${y(point.value)}`).join(' '),
)
</script>
<template>
  <svg :viewBox="`0 0 ${width} 235`" ref="svg" role="img" :aria-label="label">
    <title>{{ label }}</title>
    <template v-for="i in 5" :key="i">
      <line
        x1="52"
        :y1="y((max * (i - 1)) / 4)"
        :x2="width - 24"
        :y2="y((max * (i - 1)) / 4)"
        stroke="var(--sm-border)"
        stroke-dasharray="3 4"
      />
      <text x="44" :y="y((max * (i - 1)) / 4) + 4" text-anchor="end">
        {{ formatMin((max * (i - 1)) / 4) }}{{ percent ? '%' : '' }}
      </text>
    </template>
    <template v-if="percent">
      <line
        x1="52"
        :y1="y(100)"
        :x2="width - 24"
        :y2="y(100)"
        stroke="var(--sm-warning)"
        stroke-dasharray="6 4"
      />
      <text :x="width - 24" :y="y(100) - 8" text-anchor="end">目标 100%</text>
    </template>
    <text
      v-for="index in ticks"
      :key="index"
      :x="x(index)"
      y="215"
      :text-anchor="
        index === 0 && points.length > 1
          ? 'start'
          : index === points.length - 1 && points.length > 1
            ? 'end'
            : 'middle'
      "
    >
      {{ points[index]?.label }}
    </text>
    <polyline
      :points="polyline"
      fill="none"
      stroke="var(--sm-chart)"
      stroke-width="2.5"
      stroke-linejoin="round"
    />
    <circle
      v-for="(point, index) in points"
      :key="point.label"
      :cx="x(index)"
      :cy="y(point.value)"
      :r="points.length > 40 ? 2 : 3.5"
      fill="var(--sm-accent)"
      tabindex="0"
      :aria-label="
        point.detail || `${point.label}：${formatMin(point.value)} 分钟`
      "
      :data-date="point.label"
      :data-percent="percent ? point.value : undefined"
    >
      <title>
        {{ point.detail || `${point.label}：${formatMin(point.value)} 分钟` }}
      </title>
    </circle>
  </svg>
</template>

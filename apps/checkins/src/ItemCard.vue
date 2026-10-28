<script setup lang="ts">
import { computed } from "vue";
import {
  daily,
  duration,
  clock,
  localDay,
  timestamp,
  type Item,
} from "./model";
const props = defineProps<{
  i: Item;
  now: number;
  busy: boolean;
  ready: boolean;
}>();
const emit = defineEmits<{ check: [item: Item]; history: [item: Item] }>();
const today = computed(() => localDay(props.now));
function total(i: Item) {
  return i.type === "count"
    ? `${i.records.length} 次`
    : duration(
        i.records.reduce(
          (sum, record) => sum + (record.end ?? record.start) - record.start,
          0,
        ) +
          (i.activeSince != null ? Math.max(0, props.now - i.activeSince) : 0),
      );
}
function todayValue(i: Item) {
  const stats = daily([i], props.now);
  return i.type === "count"
    ? `${stats.counts[today.value] || 0} 次`
    : duration(stats.times[today.value] || 0);
}
</script>
<template>
  <article class="card">
    <div class="card-top">
      <span class="badge" :class="{ timer: i.type === 'timer' }">{{
        i.type === "timer" ? "◷ 按时间" : "＋ 按次数"
      }}</span
      ><span class="muted">{{
        i.activeSince != null ? "● 计时中" : `${i.records.length} 条记录`
      }}</span>
    </div>
    <h3>{{ i.name }}</h3>
    <p class="total" :data-total="i.id">{{ total(i) }}</p>
    <p class="muted" :data-today="i.id">
      累计{{ i.type === "timer" ? "投入" : "打卡" }} · 今日
      {{ todayValue(i) }}
    </p>
    <p v-if="i.activeSince != null" class="muted">
      本次
      <strong :data-clock="i.id">{{ clock(now - i.activeSince) }}</strong> ·
      {{ timestamp(i.activeSince) }} 开始
    </p>
    <p v-else class="muted">
      {{
        i.records.length
          ? "最近：" +
            timestamp(
              i.records[i.records.length - 1]!.end ??
                i.records[i.records.length - 1]!.start,
            )
          : "从今天的第一次开始"
      }}
    </p>
    <button
      class="button action"
      :class="{ running: i.activeSince != null }"
      data-action="check"
      :data-id="i.id"
      :disabled="busy || !ready"
      @click="emit('check', i)"
    >
      {{
        i.type === "count"
          ? "+1 打卡"
          : i.activeSince != null
            ? "■ 结束计时"
            : "▷ 开始计时"
      }}</button
    ><button
      class="link detail"
      data-action="history"
      :data-id="i.id"
      @click="emit('history', i)"
    >
      查看记录 ↗
    </button>
  </article>
</template>

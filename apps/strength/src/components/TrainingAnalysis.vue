<script setup lang="ts">
import { computed, ref } from "vue";
import LineChart from "../../../shared/LineChart.vue";
import type { Exercise, TrainingLog } from "../model";
const props = defineProps<{ exercises: Exercise[]; logs: TrainingLog[] }>();
const selected = ref(props.exercises[0].id),
  metric = ref("volume");
const best = computed(() =>
  props.exercises
    .filter((e) => props.logs.some((l) => l.exId === e.id))
    .map((e) => {
      const logs = props.logs.filter((l) => l.exId === e.id);
      return {
        ...e,
        best: Math.max(...logs.map((l) => l.weight)),
        quantity: Math.max(...logs.map((l) => l.reps)),
        rm: Math.max(
          0,
          ...logs
            .filter((l) => l.unit !== "秒" && l.weight > 0 && l.reps <= 30)
            .map((l) => l.weight * (1 + l.reps / 30)),
        ),
      };
    }),
);
const trend = computed(() => {
  const by = new Map<string, number>();
  for (const l of props.logs.filter((l) => l.exId === selected.value)) {
    if (l.unit === "秒" && ["volume", "est1rm"].includes(metric.value))
      continue;
    const v =
      metric.value === "volume"
        ? l.sets * l.reps * l.weight
        : metric.value === "best"
          ? l.weight
          : metric.value === "reps"
            ? l.reps
            : l.weight > 0 && l.reps <= 30
              ? l.weight * (1 + l.reps / 30)
              : 0;
    by.set(
      l.date,
      metric.value === "volume"
        ? (by.get(l.date) || 0) + v
        : Math.max(by.get(l.date) || 0, v),
    );
  }
  return [
    {
      name: "力量趋势",
      points: [...by].sort().map(([date, value]) => ({ date, value })),
    },
  ];
});
const weeks = computed(() => {
  const by = new Map<string, number>();
  for (const l of props.logs) {
    const d = new Date(l.date + "T12:00:00");
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const date = [
      d.getFullYear(),
      String(d.getMonth() + 1).padStart(2, "0"),
      String(d.getDate()).padStart(2, "0"),
    ].join("-");
    by.set(date, (by.get(date) || 0) + l.sets);
  }
  return [
    {
      name: "每周训练组数",
      points: [...by].sort().map(([date, value]) => ({ date, value })),
    },
  ];
});
</script>
<template>
  <section class="sm-panel">
    <div class="section-heading">
      <h2>力量趋势</h2>
      <div class="actions">
        <select id="trendEx" v-model="selected" class="sm-control">
          <option v-for="e in exercises" :key="e.id" :value="e.id">
            {{ e.name }}
          </option></select
        ><select id="trendMetric" v-model="metric" class="sm-control">
          <option value="volume">训练容量 kg·次</option>
          <option value="best">最高负重</option>
          <option value="reps">最大单组数量</option>
          <option value="est1rm">估算 1RM</option>
        </select>
      </div>
    </div>
    <LineChart :series="trend" label="力量趋势" />
    <p class="muted">
      计时动作不计算容量或估算 1RM；1RM 仅统计 30 次以内的负重记录。
    </p>
  </section>
  <div class="two-columns">
    <section class="sm-panel">
      <h2>历史最佳</h2>
      <div id="bestTable" class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>动作</th>
              <th>最高重量</th>
              <th>最大单组数量</th>
              <th>最高估算 1RM</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in best" :key="e.id">
              <td>{{ e.name }}</td>
              <td>{{ e.best }} kg</td>
              <td>{{ e.quantity }}{{ e.unit }}</td>
              <td>{{ e.rm ? e.rm.toFixed(2) : "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <section class="sm-panel">
      <h2>每周训练组数</h2>
      <LineChart :series="weeks" label="每周训练组数" />
    </section>
  </div>
</template>

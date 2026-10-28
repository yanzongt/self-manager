<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import Chart from "./Chart.vue";
import ItemCard from "./ItemCard.vue";
import { useCheckins } from "./useCheckins";
import {
  daily,
  duration,
  localDay,
  timestamp,
  type Item,
  type ItemType,
} from "./model";
const { state, ready, busy, message, error, addItem, check } = useCheckins();
const filter = ref("all"),
  selected = ref("all"),
  range = ref(7),
  now = ref(Date.now());
const name = ref(""),
  type = ref<ItemType>("count"),
  addDialog = ref<HTMLDialogElement | null>(null),
  historyDialog = ref<HTMLDialogElement | null>(null),
  history = ref<Item | null>(null),
  nameInput = ref<HTMLInputElement | null>(null);
const stats = computed(() => daily(state.value.items, now.value)),
  today = computed(() => localDay(now.value)),
  visible = computed(() =>
    state.value.items.filter(
      (i) => filter.value === "all" || i.type === filter.value,
    ),
  );
const chartStats = computed(() =>
  daily(
    state.value.items.filter(
      (i) => selected.value === "all" || i.id === selected.value,
    ),
    now.value,
  ),
);
const minutes = computed(() =>
  Object.fromEntries(
    Object.entries(chartStats.value.times).map(([k, v]) => [k, v / 60000]),
  ),
);
const days = computed(() =>
  Array.from({ length: range.value }, (_, i) => {
    const d = new Date(now.value);
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - (range.value - 1 - i));
    return localDay(d);
  }),
);
function openAdd() {
  name.value = "";
  type.value = "count";
  addDialog.value?.showModal();
  nameInput.value?.focus();
}
function add() {
  const n = name.value.trim();
  if (!n) {
    nameInput.value?.setCustomValidity("请输入事项名称");
    nameInput.value?.reportValidity();
    return;
  }
  addDialog.value?.close();
  void addItem(n, type.value);
}

function showHistory(i: Item) {
  history.value = i;
  historyDialog.value?.showModal();
}
let timer: ReturnType<typeof setInterval>;
onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
});
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <header class="sm-header sm-container">
    <div class="sm-brand"><span class="sm-mark">s</span>Self Manager / 日常打卡</div>
    <a href="/" class="sm-back">← 返回主页</a>
  </header>
  <main class="sm-container">
    <section class="intro">
      <div>
        <p class="sm-eyebrow">SMALL STEPS, EVERY DAY</p>
        <h1 class="sm-title">每一次坚持，都算数。</h1>
        <p class="muted">记录行动与投入，让日常的积累清晰可见。</p>
      </div>
      <button
        id="add"
        class="button primary"
        :disabled="!ready || busy"
        @click="openAdd"
      >
        ＋ 添加事项
      </button>
    </section>
    <div id="status" role="status" aria-live="polite" :class="{ error }">
      {{ message }}
    </div>
    <section class="summary" aria-label="今日概览">
      <div class="stat">
        <span>打卡事项</span
        ><strong id="item-count">{{ ready ? state.items.length : "—" }}</strong>
      </div>
      <div class="stat">
        <span>今日计次</span
        ><strong id="today-count">{{
          ready ? (stats.counts[today] || 0) + " 次" : "—"
        }}</strong>
      </div>
      <div class="stat">
        <span>今日投入</span
        ><strong id="today-time">{{
          ready ? duration(stats.times[today] || 0) : "—"
        }}</strong>
      </div>
    </section>
    <div class="section-head">
      <h2>我的事项</h2>
      <div class="filters" aria-label="事项筛选">
        <button
          v-for="f in [
            { id: 'all', label: '全部' },
            { id: 'count', label: '按次数' },
            { id: 'timer', label: '按时间' },
          ]"
          :key="f.id"
          class="button"
          :data-filter="f.id"
          :aria-pressed="filter === f.id"
          @click="filter = f.id"
        >
          {{ f.label }}
        </button>
      </div>
    </div>
    <section id="cards" class="cards" aria-label="打卡事项">
      <ItemCard
        v-for="i in visible"
        :key="i.id"
        :i="i"
        :now="now"
        :busy="busy"
        :ready="ready"
        @check="check"
        @history="showHistory"
      />
      <div v-if="!visible.length" class="empty">
        <strong>{{
          state.items.length
            ? "这个分类还没有事项"
            : "为想坚持的事，留一个位置。"
        }}</strong
        >点击「添加事项」，开始记录你的每一小步。
      </div>
    </section>
    <section class="panel">
      <div class="section-head" style="margin-top: 0">
        <div>
          <h2>每天的积累</h2>
          <p class="muted">按本地日期统计，跨午夜的计时自动分摊。</p>
        </div>
        <div>
          <select id="chart-item" v-model="selected" aria-label="统计事项">
            <option value="all">所有事项</option>
            <option v-for="i in state.items" :key="i.id" :value="i.id">
              {{ i.name }}
            </option>
          </select>
          <select id="range" v-model.number="range" aria-label="统计天数">
            <option :value="7">最近 7 天</option>
            <option :value="30">最近 30 天</option>
          </select>
        </div>
      </div>
      <div class="chart-grid">
        <div>
          <div class="legend">
            <span><i></i>每日次数 · 次</span>
          </div>
          <div id="count-chart" class="chart-wrap">
            <Chart
              :days="days"
              :values="chartStats.counts"
              unit="次"
              color="var(--sm-chart)"
            />
          </div>
        </div>
        <div>
          <div class="legend">
            <span><i class="amber"></i>每日时长 · 分钟</span>
          </div>
          <div id="time-chart" class="chart-wrap">
            <Chart :days="days" :values="minutes" unit="分钟" color="var(--sm-chart-secondary)" />
          </div>
        </div>
      </div>
    </section>
  </main>
  <footer class="sm-container">
    记录保存在本机 data/checkins.json ·
    计时中的事项在刷新或关闭页面后仍会继续，返回后点击结束。
  </footer>
  <dialog id="add-dialog" ref="addDialog">
    <form id="add-form" @submit.prevent="add">
      <h2>添加打卡事项</h2>
      <label for="name">事项名称</label
      ><input
        id="name"
        ref="nameInput"
        v-model="name"
        maxlength="80"
        placeholder="例如：喝水、阅读、练琴"
        required
        autocomplete="off"
        @input="nameInput?.setCustomValidity('')"
      /><label for="type">打卡类型</label
      ><select id="type" v-model="type">
        <option value="count">按次数 · 每次点击 +1</option>
        <option value="timer">按时间 · 点击开始 / 结束</option>
      </select>
      <p class="muted" style="margin-top: 12px">
        每次打卡会保留时间记录，并计入每日图表。
      </p>
      <div class="dialog-actions">
        <button
          id="cancel"
          type="button"
          class="button"
          @click="addDialog?.close()"
        >
          取消</button
        ><button class="button primary" type="submit">添加事项</button>
      </div>
    </form>
  </dialog>
  <dialog id="history-dialog" ref="historyDialog">
    <div class="section-head" style="margin-top: 0">
      <h2 id="history-title">{{ history?.name }} · 打卡记录</h2>
      <button id="close-history" class="button" @click="historyDialog?.close()">
        关闭
      </button>
    </div>
    <template v-if="history"
      ><p id="history-summary" class="muted">
        共 {{ history.records.length }} 条已完成记录{{
          history.activeSince != null ? " · 另有一次计时正在进行" : ""
        }}
      </p>
      <ul id="history" class="history">
        <li v-if="history.activeSince != null">
          计时中<small>开始：{{ timestamp(history.activeSince) }}</small>
        </li>
        <li v-for="(r, k) in [...history.records].reverse()" :key="k">
          {{
            history.type === "count"
              ? "第 " + (history.records.length - k) + " 次打卡"
              : duration((r.end ?? r.start) - r.start)
          }}<small v-if="history.type === 'count'">{{
            timestamp(r.start)
          }}</small
          ><small v-else
            >开始：{{ timestamp(r.start) }}<br />结束：{{
              timestamp(r.end ?? r.start)
            }}</small
          >
        </li>
        <li v-if="!history.records.length && history.activeSince == null">
          还没有打卡记录。
        </li>
      </ul></template
    >
  </dialog>
</template>

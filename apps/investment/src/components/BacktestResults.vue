<script setup lang="ts">
import { computed, ref, watch } from "vue";
import LineChart from "../../../shared/LineChart.vue";
import { API_BASE } from "../api";
import {
  num,
  missingResearchReport,
  pct,
  strategyLabels,
  strategyColors,
  type RunDetails,
  type Strategy,
  type Result,
} from "../model";
import { tableSpecs, type Column } from "../tables";
import ResultTable from "./ResultTable.vue";
import RobustnessSummary from "./RobustnessSummary.vue";
const props = defineProps<{
  result?: RunDetails;
  dirty: boolean;
  status: string;
}>();
const emit = defineEmits<{ restore: [] }>();
const selected = ref<Strategy>("ma_band"),
  table = ref("trades"),
  mode = ref("total_return"),
  months = ref(0),
  hidden = ref<Strategy[]>([]);
watch(
  () => props.result,
  (r) => {
    if (r) {
      selected.value = (
        r.results.ma_band ? "ma_band" : Object.keys(r.results)[0]
      ) as Strategy;
      hidden.value = [];
    }
  },
  { immediate: true },
);
const entries = computed(
  () => Object.entries(props.result?.results || {}) as [Strategy, Result][],
);
const detail = computed(() => props.result?.results[selected.value]);
const summary = computed(() => detail.value?.summary || {});
const series = computed(() => {
  const all = entries.value
    .flatMap(([, r]) => r.curve.map((p) => p.date))
    .sort();
  const latest = all.at(-1);
  const limit = latest ? new Date(latest) : new Date();
  if (months.value) limit.setUTCMonth(limit.getUTCMonth() - months.value);
  return entries.value
    .filter(([s]) => !hidden.value.includes(s))
    .map(([s, r]) => ({
      name: strategyLabels[s],
      color: strategyColors[s],
      points: r.curve
        .filter(
          (p) =>
            typeof p[mode.value] === "number" &&
            (!months.value || new Date(p.date) >= limit),
        )
        .map((p) => ({ date: p.date, value: Number(p[mode.value]) })),
    }));
});
const metrics = computed(() => [
  ["最终总资产", num(summary.value.final_equity)],
  ["累计投入本金", num(summary.value.total_contributed)],
  ["累计收益率", pct(summary.value.total_return)],
  ["年化收益率", pct(summary.value.cagr)],
  ["最大回撤", pct(summary.value.max_drawdown)],
  ["累计盈亏", num(summary.value.total_pnl)],
]);
const base = computed(() =>
  props.result
    ? `${API_BASE}/api/runs/${encodeURIComponent(props.result.id)}`
    : "",
);
const comparisonRows = computed(() =>
  (props.result?.comparison || []).map((r) => ({
    ...r,
    strategy: strategyLabels[r.strategy as Strategy] || r.strategy,
  })),
);
const comparisonColumns: Column[] = [
  ["strategy", "策略", "strategy"],
  ["final_equity", "最终资产", "num"],
  ["total_contributed", "累计投入本金", "num"],
  ["total_return", "累计收益", "pct"],
  ["cagr", "年化收益", "pct"],
  ["max_drawdown", "最大回撤", "pct"],
  ["extra_return_vs_buy_hold", "相对持有", "pct"],
  ["subperiod_return_std", "子区间收益标准差", "pct"],
  ["sensitivity_worst_return_delta", "扰动最差收益变化", "pp"],
];
const tabs: Record<string, string> = {
  trades: "交易盈亏",
  fills: "成交记录",
  monthly_returns: "月度收益",
  yearly_returns: "年度收益",
  positions: "期末持仓",
  orders: "订单",
  contributions: "投入记录",
  subperiods: "独立子区间",
  sensitivity: "参数扰动",
};
function toggle(s: Strategy) {
  hidden.value = hidden.value.includes(s)
    ? hidden.value.filter((k) => k !== s)
    : [...hidden.value, s];
}
</script>
<template>
  <div class="results-area">
    <div class="section-heading">
      <span id="result-status">{{ status }}</span>
      <div class="actions">
        <button
          v-if="dirty"
          id="reuse-button"
          class="text-button"
          @click="emit('restore')"
        >
          恢复本次参数</button
        ><a
          v-if="result"
          id="download-all"
          class="sm-button"
          :href="base + '/download.zip'"
          >导出结果</a
        >
      </div>
    </div>
    <div v-if="dirty" id="dirty-banner" class="notice">
      参数已修改。当前显示的是上一次结果，重新运行后更新。
    </div>
    <div
      v-if="result?.metadata.analysis_notes?.length"
      class="notice"
      role="status"
    >
      <p v-for="note in result.metadata.analysis_notes" :key="note">
        {{ note }}
      </p>
    </div>
    <div id="metrics" class="metric-grid">
      <article
        v-for="[label, value] in metrics"
        :key="label"
        class="sm-panel metric-card"
      >
        <span class="muted">{{ label }}</span
        ><strong>{{ value }}</strong>
      </article>
    </div>
    <section class="sm-panel">
      <div class="section-heading">
        <div>
          <p class="sm-eyebrow">PERFORMANCE</p>
          <h2>策略表现</h2>
        </div>
        <div id="chart-mode" class="actions">
          <button
            v-for="(label, key) in {
              total_return: '累计收益',
              drawdown: '回撤',
              equity: '总资产',
            }"
            :key="key"
            class="sm-button"
            :class="{ 'sm-button-primary': mode === key }"
            :data-mode="key"
            @click="mode = key"
          >
            {{ label }}
          </button>
        </div>
      </div>
      <div class="section-heading">
        <div id="chart-legend" class="actions">
          <button
            v-for="[s] in entries"
            :key="s"
            class="text-button"
            :style="{
              color: strategyColors[s],
              opacity: hidden.includes(s) ? 0.4 : 1,
            }"
            :aria-pressed="!hidden.includes(s)"
            @click="toggle(s)"
          >
            ● {{ strategyLabels[s] }}
          </button>
        </div>
        <div id="chart-period" class="actions">
          <button
            v-for="(label, n) in {
              3: '3个月',
              6: '6个月',
              12: '1年',
              0: '全部',
            }"
            :key="n"
            class="text-button"
            :data-months="n"
            :aria-pressed="months === Number(n)"
            @click="months = Number(n)"
          >
            {{ label }}
          </button>
        </div>
      </div>
      <div id="chart-wrap">
        <LineChart
          :series="series"
          label="策略历史表现图"
          :percent="mode !== 'equity'"
        />
      </div>
      <p class="muted">
        {{ summary.start || "—" }} — {{ summary.end || "—" }} ·
        {{ summary.trading_days || 0 }} 个行情日
      </p>
    </section>
    <section class="sm-panel">
      <div class="section-heading">
        <h2>策略对比</h2>
        <a
          v-if="result"
          id="comparison-download"
          class="text-button"
          :href="base + '/files/comparison.csv'"
          >下载 CSV</a
        >
      </div>
      <ResultTable
        id="comparison-table"
        :rows="comparisonRows"
        :columns="comparisonColumns"
        empty="运行回测后，比较收益与风险。"
      />
    </section>
    <section class="sm-panel">
      <div class="section-heading">
        <h2>回测明细</h2>
        <select id="detail-strategy" v-model="selected" class="sm-control">
          <option v-for="[s] in entries" :key="s" :value="s">
            {{ strategyLabels[s] }}
          </option>
        </select>
      </div>
      <p id="detail-summary" class="muted">
        收益口径：{{
          summary.return_method === "time_weighted"
            ? "时间加权，剔除追加本金影响"
            : "初始本金收益"
        }}
        · 手续费 {{ num(summary.total_fees) }} · 成交 {{ summary.fills ?? "—" }}
      </p>
      <RobustnessSummary :result="detail" />
      <div id="detail-tabs" class="page-nav">
        <button
          v-for="(label, key) in tabs"
          :key="key"
          class="sm-button"
          :class="{ 'sm-button-primary': table === key }"
          :data-table="key"
          @click="table = key"
        >
          {{ label }}
        </button>
      </div>
      <ResultTable
        id="detail-table"
        :rows="detail?.tables[table] || []"
        :columns="tableSpecs[table]"
        :empty="
          table === 'subperiods' || table === 'sensitivity'
            ? missingResearchReport(table, selected, result?.metadata.config)
            : '暂无记录'
        "
      />
      <div class="section-heading">
        <span id="detail-count" class="muted"
          >共
          {{ detail?.counts[table] ?? detail?.tables[table]?.length ?? 0 }}
          条</span
        ><a
          v-if="result"
          id="detail-download"
          class="text-button"
          :href="base + '/files/' + selected + '/' + table + '.csv'"
          >下载完整 CSV</a
        >
      </div>
    </section>
    <p class="method-note muted">
      MA
      及动量信号在下一有效交易日收盘执行；买入持有在首个有效收盘日建仓。定投和自动追加资金策略采用时间加权收益，总资产包含追加本金，比较时需同时查看累计投入。数据与结果仅存储在本机。
    </p>
  </div>
</template>

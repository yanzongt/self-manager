<script setup lang="ts">
import { computed } from "vue";
import { num, pct, type Row } from "../model";
import type { Column } from "../tables";
const props = defineProps<{ rows: Row[]; columns: Column[]; empty?: string }>();
const display = computed(() => props.rows.slice(0, 500));
const translations: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  open: "持有中",
  closed: "已平仓",
  filled: "已成交",
  rejected: "已拒绝",
  pending: "待成交",
  initial: "初始投入",
  periodic: "定期追加",
  signal_top_up: "信号补足",
  signal_extra: "额外追加",
  signal_buy_budget: "信号预算买入",
  signal_sell_fraction: "信号比例卖出",
  target_weight: "目标权重",
  ok: "有效",
  invalid: "无效",
  baseline: "基准",
  buy_threshold: "买入偏离比例",
  sell_threshold: "卖出偏离比例",
  ma_window: "均线窗口",
};
function format(row: Row, [key, , type]: Column) {
  const v = row[key];
  if (v == null) return "—";
  if (type === "pct") return pct(v);
  if (type === "parameterValue") {
    if (
      [
        "buy_threshold",
        "sell_threshold",
        "threshold",
        "ma_sell_fraction",
      ].includes(String(row.parameter))
    )
      return pct(v);
    return num(v);
  }
  if (type === "pp") return num(Number(v) * 100) + " 个百分点";
  if (["num", "signed"].includes(type || "")) return num(v);
  return translations[String(v)] || String(v);
}
</script>
<template>
  <div class="table-scroll">
    <table>
      <thead>
        <tr>
          <th v-for="c in columns" :key="c[0]">{{ c[1] }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in display" :key="i">
          <td v-for="c in columns" :key="c[0]">{{ format(row, c) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="empty">{{ empty || "暂无记录" }}</p>
    <p v-if="rows.length > 500" class="muted">
      显示前 500 条，完整明细请下载 CSV。
    </p>
  </div>
</template>

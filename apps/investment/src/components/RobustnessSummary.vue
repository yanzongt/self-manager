<script setup lang="ts">
import { computed } from "vue";
import { num, pct, type Result } from "../model";
const props = defineProps<{ result?: Result }>();
const summary = computed(() => props.result?.summary || {});
const sub = computed(() => props.result?.robustness?.subperiods);
const sensitivity = computed(() => props.result?.robustness?.sensitivity);
</script>
<template>
  <div v-if="result" id="robustness-summary" class="notice">
    <p v-if="summary.ma_trade_mode === 'independent'">
      均线独立买卖 ·
      {{
        summary.ma_buy_budget_mode === "cash_plus_extra"
          ? "全部可用现金＋额外追加 " + num(summary.ma_extra_amount)
          : "每次买入总预算 " + num(summary.ma_buy_amount)
      }}
      · 每次卖出持仓 {{ pct(summary.ma_sell_fraction) }} ·
      {{
        summary.ma_funding_mode === "auto_contribute"
          ? "不足资金自动追加"
          : "按账户可用现金执行"
      }}。
    </p>
    <p v-if="summary.ma_trade_mode">
      买入{{
        summary.ma_buy_first_only ? "仅首次达到时交易" : "连续满足可重复交易"
      }}
      · 卖出{{
        summary.ma_sell_first_only ? "仅首次达到时交易" : "连续满足可重复交易"
      }}；首次模式需先退出条件区才能再次触发。
    </p>
    <template v-if="sub?.count"
      ><p>
        独立子区间 {{ sub.count }} 段 · 收益均值
        {{ pct(sub.total_return?.mean) }} · 标准差
        {{ pct(sub.total_return?.std) }} · 最差
        {{ pct(sub.total_return?.min) }} · 最好
        {{ pct(sub.total_return?.max) }} · 盈利占比
        {{ pct(sub.total_return?.positive_fraction) }}
      </p>
      <p>
        年化收益标准差 {{ pct(sub.cagr?.std) }} · 回撤标准差
        {{ pct(sub.max_drawdown?.std) }} · 跑赢持有占比
        {{ pct(sub.excess_return?.positive_fraction) }} · 无交易区间占比
        {{ pct(sub.no_trade_fraction) }}
      </p></template
    >
    <p v-if="sensitivity?.applicable">
      单因素相对扰动 ±{{ pct(sensitivity.perturbation) }} · 有效变体
      {{ sensitivity.valid_variants }} · 无效变体
      {{ sensitivity.invalid_variants }} · 收益标准差
      {{ pct(sensitivity.total_return?.std) }} · 最差收益变化
      {{
        sensitivity.worst_return_delta == null
          ? "—"
          : num(sensitivity.worst_return_delta * 100) + " 个百分点"
      }}
    </p>
    <p v-if="sub?.count || sensitivity?.applicable">
      子区间各自从初始资金回测，使用之前行情预热；标准差采用总体口径。无交易的平稳结果不代表有效，历史稳定性不能证明未来有效；固定股票池存在幸存者偏差。
    </p>
  </div>
</template>

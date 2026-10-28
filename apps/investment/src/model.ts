export const strategyLabels = {
  buy_hold: "买入持有",
  ma_band: "MA 均线策略",
  fixed_weight: "固定权重再平衡",
  cross_sectional_momentum: "截面动量策略",
  dca: "定投策略",
};
export type Strategy = keyof typeof strategyLabels;
export interface Stock {
  ticker: string;
  name: string;
  weight: number;
}
export interface BacktestConfig {
  pool: Stock[];
  strategies: Strategy[];
  period: string;
  initial_cash: number;
  fee_rate: number;
  ma_trade_mode: string;
  ma_buy_first_only: boolean;
  ma_sell_first_only: boolean;
  ma_buy_budget_mode: string;
  ma_extra_amount: number;
  ma_funding_mode: string;
  ma_buy_amount: number;
  ma_sell_fraction: number;
  ma_window: number;
  threshold: number;
  buy_threshold: number;
  sell_threshold: number;
  momentum_lookback: number;
  momentum_interval: number;
  momentum_top_n: number;
  subperiod_count: number;
  sensitivity_enabled: boolean;
  perturbation: number;
  dca_amount: number;
  dca_frequency: string;
  rebalance_frequency: string;
  data_mode: string;
}
export type Cell = string | number | boolean | null;
export type Row = Record<string, Cell>;
export interface Distribution {
  mean?: number;
  std?: number;
  min?: number;
  max?: number;
  positive_fraction?: number;
}
export interface Robustness {
  subperiods?: {
    count?: number;
    total_return?: Distribution;
    cagr?: Distribution;
    max_drawdown?: Distribution;
    excess_return?: Distribution;
    no_trade_fraction?: number;
  };
  sensitivity?: {
    applicable?: boolean;
    perturbation?: number;
    valid_variants?: number;
    invalid_variants?: number;
    total_return?: Distribution;
    worst_return_delta?: number;
  };
}
export interface Result {
  summary: Row;
  curve: ({ date: string } & Record<string, number | string | null>)[];
  tables: Record<string, Row[]>;
  counts: Record<string, number>;
  robustness?: Robustness;
}
export interface RunDetails {
  id: string;
  metadata: {
    config: LegacyConfig;
    created_at: string;
    analysis_notes?: string[];
    market_data?: { tickers: { end_date: string }[] };
  };
  results: Partial<Record<Strategy, Result>>;
  comparison: Row[];
}
export interface Run {
  id: string;
  state: string;
  created_at?: string;
  message?: string;
  strategies?: Strategy[];
  config?: LegacyConfig;
  category?: string;
}
export interface CacheEntry {
  ticker: string;
  start_date: string;
  end_date: string;
  row_count: number;
  fetched_at: string;
}
export interface Job {
  id: string;
  state: string;
  message?: string;
  progress?: number;
}
export interface Preset {
  name: string;
  saved?: boolean;
  stocks?: Record<string, string>;
  pool?: Stock[];
}
export interface ServiceConfig {
  token: string;
  capabilities: Record<string, number>;
  defaults: LegacyConfig;
  presets: Preset[];
}
export type LegacyConfig = Omit<Partial<BacktestConfig>, "pool"> & {
  pool?: Stock[] | Record<string, string>;
  weights?: Record<string, number>;
  ticker?: string;
  tickers?: string[];
  strategy?: Strategy;
};
export const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v));
export function normalizeConfig(raw: LegacyConfig = {}): BacktestConfig {
  const pool = Array.isArray(raw.pool)
    ? raw.pool
    : raw.pool
      ? Object.entries(raw.pool).map(([ticker, name]) => ({
          ticker,
          name,
          weight: raw.weights?.[ticker] ?? 1 / Object.keys(raw.pool!).length,
        }))
      : (
          raw.tickers ||
          (raw.ticker ? [raw.ticker] : ["600036.SS", "002594.SZ"])
        ).map((ticker, _, a) => ({
          ticker,
          name: ticker,
          weight: 1 / a.length,
        }));
  return clone({
    period: "5y",
    initial_cash: 100000,
    fee_rate: 0,
    ma_trade_mode: "full_position",
    ma_buy_first_only: false,
    ma_sell_first_only: false,
    ma_buy_budget_mode: "fixed",
    ma_extra_amount: 1000,
    ma_funding_mode: "cash",
    ma_buy_amount: 1000,
    ma_sell_fraction: 0.25,
    ma_window: 30,
    threshold: 0.05,
    momentum_lookback: 126,
    momentum_interval: 21,
    momentum_top_n: 1,
    subperiod_count: 0,
    sensitivity_enabled: false,
    perturbation: 0.1,
    dca_amount: 1000,
    dca_frequency: "monthly",
    rebalance_frequency: "monthly",
    data_mode: "cache",
    ...raw,
    buy_threshold: raw.buy_threshold ?? raw.threshold ?? 0.05,
    sell_threshold: raw.sell_threshold ?? raw.threshold ?? 0.05,
    strategies:
      raw.strategies ||
      (raw.strategy ? [raw.strategy] : ["buy_hold", "ma_band"]),
    pool,
  });
}
export function requestConfig(config: BacktestConfig): BacktestConfig {
  const x = clone(config);
  x.pool = x.pool.map((s) => ({
    ...s,
    ticker: s.ticker.trim().toUpperCase(),
    name: s.name.trim(),
  }));
  x.threshold = x.buy_threshold;
  if (x.ma_trade_mode !== "independent") x.ma_buy_budget_mode = "fixed";
  if (x.ma_trade_mode !== "independent" || x.ma_buy_budget_mode !== "fixed")
    x.ma_funding_mode = "cash";
  return x;
}
export function validatePool(pool: Stock[]) {
  if (
    !pool.length ||
    pool.some((s) => !s.ticker || !Number.isFinite(s.weight) || s.weight < 0)
  )
    throw Error("请补全股票代码和有效权重");
  if (new Set(pool.map((s) => s.ticker)).size !== pool.length)
    throw Error("股票池中有重复代码");
  if (pool.reduce((sum, s) => sum + s.weight, 0) > 1 + 1e-12)
    throw Error("股票权重合计不能超过 100%");
}
export function checkCapabilities(
  x: BacktestConfig,
  c: Record<string, number> = {},
) {
  const requirements: string[] = [];
  if (
    x.subperiod_count > 0 ||
    x.sensitivity_enabled ||
    x.strategies.includes("cross_sectional_momentum") ||
    x.buy_threshold !== x.sell_threshold
  )
    requirements.push("research");
  if (x.strategies.includes("dca")) requirements.push("dca");
  if (x.strategies.includes("ma_band")) {
    if (x.ma_trade_mode === "independent") requirements.push("ma_independent");
    if (x.ma_funding_mode === "auto_contribute")
      requirements.push("ma_contributions");
    if (
      x.ma_buy_first_only ||
      x.ma_sell_first_only ||
      x.ma_buy_budget_mode === "cash_plus_extra"
    )
      requirements.push("ma_entry_budget");
  }
  if (requirements.some((k) => c[k + "_version"] !== 1))
    throw Error(
      "后台版本过旧，无法执行所选参数。请重启 ./start.sh 后重新运行。",
    );
}
export const num = (v: unknown) =>
  v == null || !Number.isFinite(Number(v))
    ? "—"
    : Number(v).toLocaleString("zh-CN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
export const pct = (v: unknown) =>
  v == null ? "—" : num(Number(v) * 100) + "%";
export const stateLabels: Record<string, string> = {
  queued: "等待运行",
  running: "正在运行",
  succeeded: "已完成",
  failed: "运行失败",
  interrupted: "运行中断",
};
export const strategyColors: Record<Strategy, string> = {
  buy_hold: "var(--sm-info)",
  ma_band: "var(--sm-chart)",
  fixed_weight: "var(--sm-chart-secondary)",
  dca: "var(--sm-warning)",
  cross_sectional_momentum: "var(--sm-accent)",
};

export function missingResearchReport(
  table: string,
  strategy: Strategy,
  config: LegacyConfig = {},
) {
  if (table === "subperiods")
    return config.subperiod_count && config.subperiod_count > 0
      ? "本次配置已启用子区间分析，但结果中缺少报告。请重启后台服务并重新运行回测。"
      : "当前显示的这次回测未启用子区间分析；修改参数后请重新运行回测。";
  if (!["ma_band", "cross_sectional_momentum"].includes(strategy))
    return "此策略没有适用的扰动参数；请选择均线或截面动量策略。";
  return config.sensitivity_enabled
    ? "本次配置已启用参数扰动，但结果中缺少报告。请重启后台服务并重新运行回测。"
    : "当前显示的这次回测未启用参数扰动；勾选后请重新运行回测。";
}

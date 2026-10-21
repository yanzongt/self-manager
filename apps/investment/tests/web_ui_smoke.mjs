/** Optional DOM logic test (not a real-browser layout test).
 * npm install --prefix /tmp/f-analysis-dom-test --no-audit --no-fund happy-dom
 * HAPPY_DOM_MODULE=/tmp/f-analysis-dom-test/node_modules/happy-dom/lib/index.js node tests/web_ui_smoke.mjs
 * All API responses here are fixtures; no network requests or real backtests are made.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import { pathToFileURL } from "node:url";
const { Window } = await import(
  process.env.HAPPY_DOM_MODULE
    ? pathToFileURL(process.env.HAPPY_DOM_MODULE).href
    : "happy-dom"
);
const root = new URL("../", import.meta.url);
const window = new Window({
  url: "http://127.0.0.1:8766",
  settings: { disableJavaScriptFileLoading: true, disableCSSFileLoading: true },
});
window.document.write(
  fs.readFileSync(new URL("f_analysis/web_static/index.html", root), "utf8"),
);
const $ = (selector) => window.document.querySelector(selector);
const defaults = {
  pool: [
    { ticker: "600036.SS", name: "招商银行", weight: 0.5 },
    { ticker: "002594.SZ", name: "比亚迪", weight: 0.5 },
  ],
  strategies: ["buy_hold", "ma_band"],
  period: "5y",
  initial_cash: 100000,
  fee_rate: 0,
  ma_window: 30,
  threshold: 0.05,
  rebalance_frequency: "monthly",
  data_mode: "cache",
};
let submitted = 0;
let payload,
  detail,
  polls = 0;
const config = {
  capabilities: {research_version: 1},
  token: "test-token",
  presets: [{ name: "example", stocks: { "600036.SS": "招商银行" } }],
  defaults,
};
const summary = {
  start: "2024-01-01",
  end: "2024-01-03",
  trading_days: 3,
  final_equity: 105000,
  total_pnl: 5000,
  total_return: 0.05,
  cagr: 0.02,
  max_drawdown: -0.02,
};
const curve = [
  { date: "2024-01-01", equity: 100000, total_return: 0, drawdown: 0 },
  { date: "2024-01-02", equity: 110000, total_return: 0.1, drawdown: 0 },
  {
    date: "2024-01-03",
    equity: 105000,
    total_return: 0.05,
    drawdown: -0.04545,
  },
];
function makeDetail() {
  const tables = {
    trades: [
      {
        ticker: "600036.SS",
        entry_date: "2024-01-01",
        quantity: 10,
        pnl: 50,
        return: 0.05,
        status: "open",
      },
    ],
    fills: [],
    positions: [],
    orders: [],
    subperiods: [{subperiod: 1, start: "2024-01-01", end: "2024-01-02", total_return: 0.1}],
    sensitivity: [{parameter: "baseline", status: "ok", total_return: 0.05},
                  {parameter: "buy_threshold", base_value: 0.05, value: 0.045, status: "ok", total_return: 0.02, return_delta: -0.03}],
    monthly_returns: [
      {
        date: "2024-01-31",
        ending_equity: 105000,
        pnl: 5000,
        return: 0.05,
        cumulative_pnl: 5000,
      },
    ],
  };
  return {
    id: "web_backtest__fixture",
    metadata: {
      created_at: "2024-01-03T00:00:00+08:00",
      config: {
        ...payload,
        pool: Object.fromEntries(
          payload.pool.map((stock) => [stock.ticker, stock.name]),
        ),
        weights: Object.fromEntries(
          payload.pool.map((stock) => [stock.ticker, stock.weight]),
        ),
      },
    },
    results: Object.fromEntries(
      ["buy_hold", "ma_band"].map((name) => [
        name,
        {
          summary: { ...summary, strategy: name },
          robustness: {subperiods: {count: 2, total_return: {mean: 0.05, std: 0.02, min: 0.03, max: 0.07, positive_fraction: 1},
            cagr: {std: 0.02}, max_drawdown: {std: 0.01}, excess_return: {positive_fraction: 0.5}, no_trade_fraction: 0}},
          curve,
          tables,
          counts: { trades: 1, monthly_returns: 1, subperiods: 1, sensitivity: 2 },
        },
      ]),
    ),
    comparison: ["buy_hold", "ma_band"].map((strategy) => ({
      ...summary,
      strategy,
      extra_return_vs_buy_hold: 0,
    })),
  };
}
window.fetch = async (url, options = {}) => {
  let data;
  if (url === "/api/config") data = config;
  else if (url === "/api/cache")
    data = {
      items: [
        {
          ticker: "601318.SS",
          start_date: "2020-01-01",
          end_date: "2024-01-03",
          row_count: 1000,
          fetched_at: "2024-01-03T00:00:00+08:00",
        },
      ],
    };
  else if (url === "/api/pools" && options.method === "POST") {
    const saved = JSON.parse(options.body);
    assert.equal(options.headers["X-Local-Token"], "test-token");
    assert.equal(saved.name, "长期配置");
    data = { name: saved.name, presets: [...config.presets, { name: saved.name, pool: saved.pool, saved: true }] };
  }
  else if (url === "/api/runs" && options.method === "POST") {
    submitted += 1;
    payload = JSON.parse(options.body);
    assert.equal(options.headers["X-Local-Token"], "test-token");
    detail = makeDetail();
    data = { id: detail.id };
  } else if (url === "/api/runs")
    data = {
      items: detail
        ? [
            {
              id: detail.id,
              state: "succeeded",
              created_at: detail.metadata.created_at,
              config: detail.metadata.config,
              source: "web_backtest",
            },
          ]
        : [],
    };
  else if (url.startsWith("/api/jobs/"))
    data = {
      id: detail.id,
      state: ++polls > 1 ? "succeeded" : "running",
      progress: polls > 1 ? 100 : 50,
      message: "测试任务",
    };
  else if (url === "/api/runs/web_backtest__fixture") data = detail;
  else throw new Error(`Unexpected request: ${url}`);
  return { ok: true, json: async () => structuredClone(data) };
};
const waitFor = async (predicate) => {
  const deadline = Date.now() + 6000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("DOM test timed out");
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
};
try {
  window.eval(
    fs.readFileSync(new URL("f_analysis/web_static/app.js", root), "utf8"),
  );
  await waitFor(
    () =>
      $("#connection-text").textContent === "本机引擎已连接" &&
      window.document.querySelectorAll(".pool-row").length === 2,
  );
  assert.equal($("#global-error").hidden, true);
  assert.equal($("#chart-empty").hidden, false);
  $("#add-stock").click();
  assert.equal(window.document.querySelectorAll(".pool-row").length, 3);
  window.document.querySelectorAll(".remove-stock")[2].click();
  assert.equal(window.document.querySelectorAll(".pool-row").length, 2);
  $('[data-ma="120"]').click();
  assert.equal($("#ma-window").value, "120");
  assert.match($("#ma-rule").textContent, /MA120/);
  $("#equal-weights").click();
  assert.equal($("#cash-weight").textContent, "0%");
  $("#pool-name").value = "长期配置";
  const weights = window.document.querySelectorAll(".stock-weight");
  weights[0].value = "30";
  weights[1].value = "20";
  $("#save-pool").click();
  await waitFor(() => $("#pool-preset").value === "长期配置" && !$("#save-pool").disabled);
  weights[0].value = "90";
  $("#pool-preset").dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.equal(window.document.querySelectorAll(".stock-weight")[0].value, "30");
  assert.equal(window.document.querySelectorAll(".stock-weight")[1].value, "20");
  assert.equal($("#cash-weight").textContent, "50%");
  assert.equal($("#ma-window").value, "120");
  $("#equal-weights").click();
  $("#data-mode").value = "offline";
  $("#data-mode").dispatchEvent(new window.Event("change", { bubbles: true }));
  $('input[value="cross_sectional_momentum"]').click();
  assert.equal($("#momentum-options").hidden, false);
  $("#momentum-lookback").value = "63";
  $("#momentum-interval").value = "10";
  $("#sell-threshold").value = "8";
  $("#subperiod-count").value = "5";
  $("#sensitivity-enabled").click();
  assert.equal($("#perturbation").disabled, false);
  // A refreshed frontend must not submit new research fields to an old Python process.
  delete config.capabilities;
  $("#backtest-form").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await waitFor(() => $("#form-error").textContent.includes("后台服务版本过旧"));
  assert.equal(submitted, 0);
  assert.equal($("#run-button").disabled, false);
  config.capabilities = {research_version: 1};
  $("#backtest-form").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await waitFor(() => !$("#download-all").hidden && !$("#run-button").disabled);
  assert.equal(payload.ma_window, 120);
  assert.equal(payload.buy_threshold, 0.05);
  assert.equal(payload.sell_threshold, 0.08);
  assert.equal(payload.momentum_lookback, 63);
  assert.equal(payload.momentum_interval, 10);
  assert.equal(payload.subperiod_count, 5);
  assert.equal(payload.sensitivity_enabled, true);
  assert.equal(payload.perturbation, 0.1);
  assert.ok(payload.strategies.includes("cross_sectional_momentum"));
  assert.match($("#robustness-summary").textContent, /标准差/);
  $('[data-table="subperiods"]').click();
  assert.match($("#detail-table").textContent, /2024-01-01/);
  $('[data-table="sensitivity"]').click();
  assert.match($("#detail-table").textContent, /买入偏离比例/);
  assert.match($("#detail-table").textContent, /4.50%/);
  assert.match($("#detail-download").href, /sensitivity.csv/);
  assert.equal(payload.data_mode, "offline");
  assert.equal($("#chart-empty").hidden, true);
  assert.equal($("#comparison-table tbody").children.length, 2);
  assert.match($("#metrics").textContent, /105,000/);
  assert.equal($("#chart").querySelectorAll("path").length, 2);
  $("#chart-legend button").click();
  assert.equal($("#chart").querySelectorAll("path").length, 1);
  $('[data-mode="drawdown"]').click();
  assert.equal($("#chart").querySelectorAll("path").length, 1);
  $('[data-table="monthly_returns"]').click();
  assert.match($("#detail-table").textContent, /2024-01/);
  $('[data-ma="60"]').click();
  assert.equal($("#dirty-banner").hidden, false);
  $("#reuse-button").click();
  assert.equal($("#ma-window").value, "120");
  assert.equal($("#sell-threshold").value, "8");
  assert.equal($("#momentum-lookback").value, "63");
  assert.equal($("#sensitivity-enabled").checked, true);
  assert.equal($("#dirty-banner").hidden, true);
  $('[data-view="cache"]').click();
  await waitFor(() =>
    $("#cache-table tbody").textContent.includes("601318.SS"),
  );
  $("#cache-table button").click();
  assert.equal(window.document.querySelectorAll(".pool-row").length, 3);
  assert.equal($("#workspace-view").hidden, false);
  $('[data-view="history"]').click();
  await waitFor(() => !!$(".history-item"));
  $(".history-item button").click();
  await waitFor(
    () =>
      $("#workspace-view").hidden === false &&
      window.document.querySelectorAll(".pool-row").length === 2,
  );
  assert.equal($("#global-error").hidden, true);
  assert.match(window.missingResearchReport("subperiods", "ma_band", {subperiod_count: 5}), /已启用.*缺少报告/);
  assert.match(window.missingResearchReport("subperiods", "ma_band", {}), /当前显示的这次回测未启用/);
  assert.match(window.missingResearchReport("sensitivity", "ma_band", {sensitivity_enabled: true}), /已启用.*缺少报告/);
  assert.match(window.missingResearchReport("sensitivity", "buy_hold", {sensitivity_enabled: true}), /没有适用的扰动参数/);
  console.log(
    "Frontend DOM smoke passed: setup, saved stock pools and weights, MA120, submission, progress, chart toggles, tables, dirty-state, history and cache.",
  );
} catch (error) {
  console.error(
    "DOM debug:",
    $("#connection-text")?.textContent,
    $("#global-error")?.textContent,
    window.document.querySelectorAll(".pool-row").length,
  );
  throw error;
} finally {
  await window.happyDOM.close();
}

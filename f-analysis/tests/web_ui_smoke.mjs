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
let payload,
  detail,
  polls = 0;
const config = {
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
          curve,
          tables,
          counts: { trades: 1, monthly_returns: 1 },
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
  else if (url === "/api/runs" && options.method === "POST") {
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
  $("#data-mode").value = "offline";
  $("#data-mode").dispatchEvent(new window.Event("change", { bubbles: true }));
  $("#backtest-form").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await waitFor(() => !$("#download-all").hidden && !$("#run-button").disabled);
  assert.equal(payload.ma_window, 120);
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
  console.log(
    "Frontend DOM smoke passed: setup, stock pool, MA120, submission, progress, chart toggles, tables, dirty-state, history and cache.",
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

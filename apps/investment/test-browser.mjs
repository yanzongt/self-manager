// Real Chromium regression test. API fixtures isolate browser behavior from market downloads.
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
const staticRoot = fileURLToPath(
  new URL(".generated/static/", import.meta.url),
);
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
  capabilities: {
    research_version: 1,
    dca_version: 1,
    ma_independent_version: 1,
    ma_contributions_version: 1,
    ma_entry_budget_version: 1,
  },
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
    contributions: [
      {
        date: "2024-01-01",
        kind: "initial",
        amount: 100000,
        total_contributed: 100000,
      },
    ],
    subperiods: [
      {
        subperiod: 1,
        start: "2024-01-01",
        end: "2024-01-02",
        total_return: 0.1,
      },
    ],
    sensitivity: [
      { parameter: "baseline", status: "ok", total_return: 0.05 },
      {
        parameter: "buy_threshold",
        base_value: 0.05,
        value: 0.045,
        status: "ok",
        total_return: 0.02,
        return_delta: -0.03,
      },
    ],
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
      [
        "buy_hold",
        "ma_band",
        ...(payload.strategies.includes("dca") ? ["dca"] : []),
      ].map((name) => [
        name,
        {
          summary: {
            ...summary,
            strategy: name,
            return_method: name === "dca" ? "time_weighted" : "initial_capital",
            total_contributed: 100000,
          },
          robustness: {
            subperiods: {
              count: 2,
              total_return: {
                mean: 0.05,
                std: 0.02,
                min: 0.03,
                max: 0.07,
                positive_fraction: 1,
              },
              cagr: { std: 0.02 },
              max_drawdown: { std: 0.01 },
              excess_return: { positive_fraction: 0.5 },
              no_trade_fraction: 0,
            },
          },
          curve,
          tables,
          counts: {
            contributions: 1,
            trades: 1,
            monthly_returns: 1,
            subperiods: 1,
            sensitivity: 2,
          },
        },
      ]),
    ),
    comparison: [
      "buy_hold",
      "ma_band",
      ...(payload.strategies.includes("dca") ? ["dca"] : []),
    ].map((strategy) => ({
      ...summary,
      strategy,
      extra_return_vs_buy_hold: 0,
    })),
  };
}

const server = http.createServer(async (req, res) => {
  const resource = req.url.replace(/^\/investment/, "");
  try {
    const file = path.join(
      staticRoot,
      resource === "/" ? "index.html" : resource,
    );
    res.setHeader(
      "Content-Type",
      file.endsWith(".js")
        ? "text/javascript"
        : file.endsWith(".css")
          ? "text/css"
          : "text/html",
    );
    res.end(await fs.readFile(file));
  } catch {
    res.statusCode = 404;
    res.end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox"],
});
const errors = [];
try {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", (d) => d.accept());
  let active = false,
    fail = false,
    delayJob = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()).pathname.replace(/^\/investment/, "");
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
            fetched_at: "2024-01-03",
          },
        ],
      };
    else if (url === "/api/pools") {
      const saved = request.postDataJSON();
      assert.equal(request.headers()["x-local-token"], "test-token");
      assert.equal(saved.name, "长期配置");
      config.presets.push({ name: saved.name, pool: saved.pool, saved: true });
      data = { name: saved.name, presets: config.presets };
    } else if (url === "/api/runs" && request.method() === "POST") {
      submitted++;
      payload = request.postDataJSON();
      detail = makeDetail();
      active = true;
      data = { id: detail.id };
    } else if (url === "/api/runs")
      data = {
        items: active
          ? [
              {
                id: "web_backtest__fixture",
                state: fail ? "failed" : "succeeded",
                created_at: "2024-01-03",
              },
            ]
          : [],
      };
    else if (url.startsWith("/api/jobs/")) {
      polls++;
      data = {
        id: "web_backtest__fixture",
        state: delayJob ? "running" : fail ? "failed" : "succeeded",
        progress: delayJob ? 40 : 100,
        message: fail ? "缓存缺少股票" : "回测完成",
      };
    } else if (url === "/api/runs/web_backtest__fixture") data = detail;
    else
      return route.fulfill({ status: 404, json: { error: "missing fixture" } });
    await route.fulfill({ json: data });
  });
  const text = (selector) => page.textContent(selector);
  const waitText = (selector, value) =>
    page.waitForFunction(
      ({ selector, value }) =>
        document.querySelector(selector)?.textContent.includes(value),
      { selector, value },
    );
  await page.goto(`http://127.0.0.1:${server.address().port}/investment/`);
  await waitText("#connection-text", "本机引擎已连接");
  await page.waitForSelector(".pool-row");
  assert.equal(await page.locator(".pool-row").count(), 2);
  await page.click("#add-stock");
  assert.equal(await page.locator(".pool-row").count(), 3);
  await page.locator(".remove-stock").last().click();
  await page.click('[data-ma="120"]');
  assert.equal(await page.inputValue("#ma-window"), "120");
  await page.fill("#pool-name", "长期配置");
  await page.locator(".stock-weight").nth(0).fill("30");
  await page.locator(".stock-weight").nth(1).fill("20");
  await page.click("#save-pool");
  await page.waitForSelector('#pool-preset option[value="长期配置"]', {
    state: "attached",
  });
  await page.locator(".stock-weight").nth(0).fill("90");
  await page.selectOption("#pool-preset", "长期配置");
  assert.equal(await page.locator(".stock-weight").nth(0).inputValue(), "30");
  assert.equal(await text("#cash-weight"), "50.00%");
  await page.click("#equal-weights");
  await page.selectOption("#data-mode", "offline");
  await page.check('input[value="cross_sectional_momentum"]');
  await page.fill("#momentum-lookback", "63");
  await page.fill("#momentum-interval", "10");
  await page.fill("#sell-threshold", "8");
  await page.fill("#subperiod-count", "5");
  await page.check("#sensitivity-enabled");
  await page.check('input[value="dca"]');
  await page.fill("#dca-amount", "500");
  await page.selectOption("#dca-frequency", "weekly");
  const capabilities = { ...config.capabilities };
  config.capabilities = {};
  await page.click("#run-button");
  await waitText("#global-error", "后台版本过旧");
  assert.equal(submitted, 0);
  config.capabilities = capabilities;
  await page.selectOption("#ma-trade-mode", "independent");
  await page.fill("#ma-buy-amount", "2000");
  await page.fill("#ma-sell-fraction", "40");
  await page.selectOption("#ma-funding-mode", "auto_contribute");
  await page.selectOption("#ma-buy-budget-mode", "cash_plus_extra");
  await page.fill("#ma-extra-amount", "250");
  await page.check("#ma-buy-first-only");
  await page.check("#ma-sell-first-only");
  delayJob = true;
  await page.click("#run-button");
  await waitText("#job-percent", "40%");
  // Edits during a background job must survive the completed result.
  await page.click('[data-ma="60"]');
  delayJob = false;
  await page.waitForSelector("#download-all");
  await page.waitForSelector("#dirty-banner");
  assert.equal(await page.inputValue("#ma-window"), "60");
  await page.click("#reuse-button");
  assert.equal(await page.inputValue("#ma-window"), "120");
  for (const [key, value] of Object.entries({
    ma_funding_mode: "cash",
    ma_buy_budget_mode: "cash_plus_extra",
    ma_extra_amount: 250,
    ma_buy_first_only: true,
    ma_sell_first_only: true,
    ma_trade_mode: "independent",
    ma_buy_amount: 2000,
    ma_sell_fraction: 0.4,
    dca_amount: 500,
    dca_frequency: "weekly",
    ma_window: 120,
    buy_threshold: 0.05,
    sell_threshold: 0.08,
    momentum_lookback: 63,
    momentum_interval: 10,
    subperiod_count: 5,
    sensitivity_enabled: true,
    perturbation: 0.1,
    data_mode: "offline",
  }))
    assert.equal(payload[key], value, key);
  assert.ok(payload.strategies.includes("cross_sectional_momentum"));
  assert.match(await text("#metrics"), /105,000/);
  assert.equal(await page.locator("#chart-wrap polyline").count(), 3);
  await page.locator("#chart-legend button").first().click();
  assert.equal(await page.locator("#chart-wrap polyline").count(), 2);
  await page.click('[data-mode="drawdown"]');
  await page.click('[data-table="subperiods"]');
  assert.match(await text("#detail-table"), /2024-01-01/);
  await page.click('[data-table="sensitivity"]');
  assert.match(await text("#detail-table"), /买入偏离比例/);
  assert.match(
    await page.getAttribute("#detail-download", "href"),
    /sensitivity.csv/,
  );
  await page.selectOption("#detail-strategy", "dca");
  assert.match(await text("#detail-summary"), /时间加权/);
  await page.click('[data-table="contributions"]');
  assert.match(await text("#detail-table"), /初始投入/);
  await page.click('[data-view="cache"]');
  await waitText("#cache-table", "601318.SS");
  await page.click(".cache-actions button");
  assert.equal(await page.locator(".pool-row").count(), 3);
  await page.click('[data-view="history"]');
  await page.waitForSelector("[data-run]");
  await page.click("[data-run]");
  assert.equal(await page.inputValue("#ma-window"), "120");
  // Draft restore and reconnect to an unfinished job across reloads.
  await page.click('[data-ma="60"]');
  await page.waitForFunction(
    () =>
      JSON.parse(localStorage.getItem("f-analysis.draft.v1")).ma_window === 60,
  );
  await page.reload();
  await waitText("#connection-text", "本机引擎已连接");
  await page.waitForSelector("#download-all");
  assert.equal(await page.inputValue("#ma-window"), "60");
  // Reload reconnects to an active job and keeps the latest draft.
  delayJob = true;
  await page.click("#run-button");
  await waitText("#job-percent", "40%");
  await page.click('[data-ma="250"]');
  await page.waitForFunction(
    () =>
      JSON.parse(localStorage.getItem("f-analysis.draft.v1")).ma_window === 250,
  );
  await page.reload();
  await waitText("#job-percent", "40%");
  delayJob = false;
  await page.waitForSelector("#job-progress", { state: "detached" });
  assert.equal(await page.inputValue("#ma-window"), "250");
  fail = true;
  await page.click("#run-button");
  await waitText("#global-error", "缓存缺少股票");
  assert.match(await text("#metrics"), /105,000/);
  fail = false;
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: `/tmp/investment-${width}.png`,
      fullPage: true,
    });
  }
  await page.click("#help-button");
  await page.waitForSelector("#help-dialog[open]");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#help-dialog[open]").count(), 0);
  assert.deepEqual(errors, []);
  console.log(
    "Passed: Vue configuration, pools, capabilities, payloads, polling, concurrent edits, result tables, chart toggles, draft restore, failure handling, history/cache, mobile layout and dialog keyboard handling.",
  );
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}

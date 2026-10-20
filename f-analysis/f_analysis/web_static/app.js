const API_BASE = location.pathname.startsWith("/investment/") ? "/investment" : "";
"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const NS = "http://www.w3.org/2000/svg";
const labels = {
  buy_hold: "买入持有",
  ma_band: "MA 均线策略",
  fixed_weight: "固定权重再平衡",
};
const colors = {
  buy_hold: "#4266dc",
  ma_band: "#168471",
  fixed_weight: "#b98842",
};
const colorClasses = {
  buy_hold: "blue-dot",
  ma_band: "green-dot",
  fixed_weight: "amber-dot",
};
const stateLabels = {
  queued: "等待运行",
  running: "正在运行",
  succeeded: "已完成",
  failed: "运行失败",
  interrupted: "运行中断",
};
const state = {
  token: "",
  config: null,
  runs: [],
  cache: [],
  result: null,
  selected: "",
  table: "trades",
  chartMode: "total_return",
  months: 0,
  hidden: new Set(),
  dirty: false,
  running: false,
  changedWhileRunning: false,
  loading: 0,
  activeJob: null,
  busyPoll: false,
};
const num = (value, digits = 2) =>
  value == null || !Number.isFinite(Number(value))
    ? "—"
    : Number(value).toLocaleString("zh-CN", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
const pct = (value) => (value == null ? "—" : `${num(value * 100)}%`);
const signClass = (value) =>
  Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
const dateText = (value) => {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? String(value).slice(0, 10)
    : d.toLocaleDateString("zh-CN");
};
const timeText = (value) => {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? String(value)
    : d.toLocaleString("zh-CN", { hour12: false });
};
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}
function addOption(select, text, value) {
  const option = node("option", "", text);
  option.value = value;
  select.append(option);
}
function icon(id) {
  const svg = document.createElementNS(NS, "svg");
  const use = document.createElementNS(NS, "use");
  use.setAttribute("href", `#i-${id}`);
  svg.append(use);
  svg.setAttribute("aria-hidden", "true");
  return svg;
}
function showError(message, location = "#global-error") {
  const box = $(location);
  box.textContent = message;
  box.hidden = !message;
}
let toastTimer;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 3500);
}
async function api(path, options = {}) {
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: {
      ...(options.body
        ? { "Content-Type": "application/json", "X-Local-Token": state.token }
        : {}),
      ...options.headers,
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("服务返回异常，请检查终端或刷新页面。");
  }
  if (!response.ok)
    throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}
function saveDraft() {
  try {
    localStorage.setItem("f-analysis.draft.v1", JSON.stringify(formData()));
  } catch {
    /* 本地存储不可用时仍可运行 */
  }
}
function readStorage(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}
function formData() {
  return {
    pool: $$(".pool-row").map((row) => ({
      ticker: $(".stock-ticker", row).value.trim().toUpperCase(),
      name: $(".stock-name", row).value.trim(),
      weight: Number($(".stock-weight", row).value) / 100,
    })),
    strategies: $$('input[name="strategy"]:checked').map(
      (input) => input.value,
    ),
    period: $("#period").value,
    initial_cash: Number($("#initial-cash").value),
    fee_rate: Number($("#fee-rate").value) / 100,
    ma_window: Number($("#ma-window").value),
    threshold: Number($("#threshold").value) / 100,
    rebalance_frequency: $("#frequency").value,
    data_mode: $("#data-mode").value,
  };
}
function changed() {
  state.dirty =
    !!state.result && JSON.stringify(formData()) !== state.resultSignature;
  if (state.running) state.changedWhileRunning = true;
  $("#dirty-banner").hidden = !state.dirty;
  $("#reuse-button").hidden = !state.dirty;
  updateForm();
  saveDraft();
}
function addStock(stock = {}, focus = false) {
  const row = node("div", "pool-row");
  row.innerHTML =
    '<div class="stock-main"><input class="stock-name" placeholder="股票名称（可选）" maxlength="80"><input class="stock-ticker" placeholder="如 600036.SS" maxlength="32" required></div><div class="input-unit"><input type="number" class="stock-weight" min="0" max="100" step="any" required><span>%</span></div><button type="button" class="icon-button remove-stock"><svg aria-hidden="true"><use href="#i-close"/></svg></button>';
  $(".stock-name", row).value = stock.name || "";
  $(".stock-ticker", row).value = stock.ticker || "";
  $(".stock-weight", row).value = Number.isFinite(stock.weight)
    ? Number((stock.weight * 100).toFixed(6))
    : 0;
  $(".remove-stock", row).addEventListener("click", () => {
    if ($$(".pool-row").length === 1) return toast("股票池至少需要一只股票");
    row.remove();
    changed();
  });
  row.addEventListener("input", changed);
  $("#pool-rows").append(row);
  updateForm();
  if (focus) $(".stock-ticker", row).focus();
}
function updateForm() {
  const rows = $$(".pool-row");
  rows.forEach((row, i) => {
    $(".stock-name", row).setAttribute("aria-label", `股票 ${i + 1} 名称`);
    $(".stock-ticker", row).setAttribute("aria-label", `股票 ${i + 1} 代码`);
    $(".stock-weight", row).setAttribute(
      "aria-label",
      `股票 ${i + 1} 权重百分比`,
    );
    $(".remove-stock", row).setAttribute("aria-label", `移除股票 ${i + 1}`);
  });
  const total = rows.reduce(
    (sum, row) => sum + Number($(".stock-weight", row).value),
    0,
  );
  $("#pool-count").textContent = `${rows.length} 只股票`;
  $("#cash-weight").textContent =
    `${num(100 - total, 2).replace(/\.00$/, "")}%`;
  $("#cash-weight").classList.toggle(
    "invalid",
    !Number.isFinite(total) || total > 100 + 0.000001 || total < 0,
  );
  const ma = $('input[value="ma_band"]').checked;
  const fixed = $('input[value="fixed_weight"]').checked;
  $("#ma-options").hidden = !ma;
  $("#rebalance-options").hidden = !fixed;
  $("#ma-window").disabled = !ma;
  $("#threshold").disabled = !ma;
  $("#frequency").disabled = !fixed;
  $$("[data-ma]").forEach((button) =>
    button.classList.toggle(
      "selected",
      Number(button.dataset.ma) === Number($("#ma-window").value),
    ),
  );
  const w = $("#ma-window").value,
    t = Number($("#threshold").value);
  $("#ma-rule").textContent =
    `低于 MA${w} 的 ${num(100 - t, 2).replace(/\.00$/, "")}% 买入，高于 ${num(100 + t, 2).replace(/\.00$/, "")}% 卖出。`;
}
function applyConfig(config) {
  if (!config) return;
  const pool = Array.isArray(config.pool)
    ? config.pool
    : config.pool && typeof config.pool === "object"
      ? Object.entries(config.pool).map(([ticker, name]) => ({
          ticker,
          name,
          weight:
            config.weights?.[ticker] ?? 1 / Object.keys(config.pool).length,
        }))
      : (config.tickers || (config.ticker ? [config.ticker] : [])).map(
          (ticker) => ({
            ticker,
            name: ticker,
            weight: 1 / (config.tickers?.length || 1),
          }),
        );
  if (pool.length) {
    $("#pool-rows").replaceChildren();
    pool.forEach((stock) => addStock(stock));
  }
  const strategies =
    config.strategies ||
    (config.strategy ? [config.strategy] : ["buy_hold", "ma_band"]);
  $$('input[name="strategy"]').forEach((input) => {
    input.checked = strategies.includes(input.value);
  });
  const fields = {
    period: "period",
    initial_cash: "initial-cash",
    ma_window: "ma-window",
    rebalance_frequency: "frequency",
    data_mode: "data-mode",
  };
  Object.entries(fields).forEach(([key, id]) => {
    if (config[key] == null) return;
    const input = $(`#${id}`);
    if (
      input.tagName === "SELECT" &&
      ![...input.options].some((option) => option.value === String(config[key]))
    )
      addOption(input, String(config[key]), String(config[key]));
    input.value = config[key];
  });
  if (config.fee_rate != null)
    $("#fee-rate").value = Number((config.fee_rate * 100).toFixed(6));
  if (config.threshold != null)
    $("#threshold").value = Number((config.threshold * 100).toFixed(6));
  // 旧命令行记录没有行情模式，恢复为缓存优先。
  if (!config.data_mode) $("#data-mode").value = "cache";
  updateForm();
}
function navigate(view) {
  const info = {
    workspace: ["01", "策略回测", "从一个想法开始，让数据回答。"],
    history: ["02", "历史记录", "每一次研究，都值得留存。"],
    cache: ["03", "行情管理", "让行情复用，把时间留给策略。"],
  }[view];
  if (!info) return;
  $$(".view").forEach((el) => {
    el.hidden = el.id !== `${view}-view`;
  });
  $$("[data-view]").forEach((button) =>
    button.classList.toggle("active", button.dataset.view === view),
  );
  $("#page-number").textContent = info[0];
  $("#page-title").textContent = info[1];
  $("#page-subtitle").textContent = info[2];
  if (view === "history")
    refreshRuns().catch((error) => showError(error.message));
  if (view === "cache")
    refreshCache().catch((error) => showError(error.message));
  history.replaceState(null, "", `#${view}`);
  window.scrollTo({ top: 0, behavior: "instant" });
}
async function refreshRuns() {
  const data = await api("/api/runs");
  state.runs = data.items;
  renderRuns();
}
function renderRuns() {
  $("#history-count").textContent = state.runs.length;
  const container = $("#history-list");
  container.replaceChildren();
  if (!state.runs.length) {
    container.append(
      node("p", "empty-cell", "还没有回测记录。新建一组回测，开始你的研究。"),
    );
    return;
  }
  state.runs.forEach((run) => {
    const row = node("article", "history-item");
    const mark = node("div", "history-icon");
    mark.append(icon("chart"));
    const text = node("div");
    const stocks = run.config.pool
      ? Object.entries(run.config.pool)
          .map(([code, name]) =>
            Array.isArray(run.config.pool) ? name.ticker : `${name} ${code}`,
          )
          .join(" / ")
      : run.config.ticker || run.config.tickers?.join(" / ") || "股票回测";
    text.append(node("h3", "", stocks));
    const strategies = (run.config.strategies || [])
      .map((name) => labels[name] || name)
      .join(" · ");
    text.append(
      node(
        "p",
        "",
        `${timeText(run.created_at)}　${run.config.period || ""}　${strategies}`,
      ),
    );
    if (run.state === "failed" || run.state === "interrupted")
      text.append(node("p", "negative", run.message));
    const meta = node("div", "history-meta");
    meta.append(
      node(
        "span",
        `state-pill ${run.state}`,
        stateLabels[run.state] || run.state,
      ),
      node(
        "div",
        "",
        run.source === "web_backtest" ? "网页工作台" : "命令行回测",
      ),
    );
    const button = node(
      "button",
      "button secondary small-button",
      ["queued", "running"].includes(run.state)
        ? "查看进度"
        : run.state === "succeeded"
          ? "查看结果"
          : "复用参数",
    );
    button.addEventListener("click", async () => {
      navigate("workspace");
      if (run.state === "succeeded") {
        try {
          await loadRun(run.id, true);
        } catch (error) {
          showError(error.message);
        }
      } else {
        applyConfig(run.config);
        changed();
        if (["queued", "running"].includes(run.state)) beginPolling(run.id);
        else toast("已载入参数，可以重新运行");
      }
    });
    row.append(mark, text, meta, button);
    container.append(row);
  });
}
async function refreshCache() {
  const data = await api("/api/cache");
  state.cache = data.items;
  renderCache();
}
function renderCache() {
  $("#cache-total").replaceChildren(
    document.createTextNode(String(state.cache.length)),
    node("small", "", "已缓存标的"),
  );
  const body = $("#cache-table tbody");
  body.replaceChildren();
  if (!state.cache.length) {
    const row = node("tr");
    const cell = node(
      "td",
      "empty-cell",
      "尚无缓存。首次运行回测后，行情会自动保存到本机。",
    );
    cell.colSpan = 6;
    row.append(cell);
    body.append(row);
    return;
  }
  state.cache.forEach((item) => {
    const row = node("tr");
    [
      item.ticker,
      dateText(item.start_date),
      dateText(item.end_date),
      num(item.row_count, 0),
      timeText(item.fetched_at),
    ].forEach((value) => row.append(node("td", "", value)));
    const cell = node("td");
    const button = node("button", "text-button", "加入股票池");
    button.addEventListener("click", () => {
      if (formData().pool.some((stock) => stock.ticker === item.ticker))
        toast("该股票已在当前股票池中");
      else {
        addStock({ ticker: item.ticker, weight: 0 });
        changed();
        toast("已添加，请设置配置权重");
      }
      navigate("workspace");
    });
    cell.append(button);
    row.append(cell);
    body.append(row);
  });
}
async function loadRun(id, reuse = true) {
  const serial = ++state.loading;
  $("#result-status").textContent = "正在读取结果…";
  let result;
  try {
    result = await api(`/api/runs/${encodeURIComponent(id)}`);
  } catch (error) {
    if (serial === state.loading)
      $("#result-status").textContent = "结果读取失败";
    throw error;
  }
  if (serial !== state.loading) return;
  state.result = result;
  state.selected = result.results.ma_band
    ? "ma_band"
    : Object.keys(result.results)[0];
  state.hidden.clear();
  if (reuse) {
    applyConfig(result.metadata.config);
    state.resultSignature = JSON.stringify(formData());
    state.dirty = false;
    saveDraft();
  } else {
    const draft = formData();
    applyConfig(result.metadata.config);
    state.resultSignature = JSON.stringify(formData());
    applyConfig(draft);
    state.dirty = JSON.stringify(formData()) !== state.resultSignature;
  }
  $("#dirty-banner").hidden = !state.dirty;
  $("#reuse-button").hidden = !state.dirty;
  $("#download-all").hidden = false;
  $("#download-all").href = `${API_BASE}/api/runs/${id}/download.zip`;
  $("#comparison-download").hidden = false;
  $("#comparison-download").href = `${API_BASE}/api/runs/${id}/files/comparison.csv`;
  const select = $("#detail-strategy");
  select.replaceChildren();
  Object.keys(result.results).forEach((name) =>
    addOption(select, labels[name], name),
  );
  select.value = state.selected;
  const summary = result.results[state.selected].summary;
  $("#result-status").textContent =
    `已完成 · ${summary.trading_days} 个行情日 · ${timeText(result.metadata.created_at)}`;
  $("#result-dot").classList.remove("muted-dot");
  $("#chart-date-range").textContent = `${summary.start} — ${summary.end}`;
  const ranges = result.metadata.market_data?.tickers || [];
  const warning = result.metadata.analysis_notes;
  if (warning?.length) toast(warning.join("；"));
  $("#curve-info").textContent = ranges.length
    ? `数据截止 ${ranges.map((item) => item.end_date).sort()[0]}`
    : "点击图例可隐藏曲线";
  renderMetrics();
  renderComparison();
  renderDetails();
  renderLegend();
  renderChart();
}
function renderMetrics() {
  if (!state.result) return;
  const summary = state.result.results[state.selected].summary;
  const hold = state.result.results.buy_hold?.summary;
  const extra = hold ? summary.total_return - hold.total_return : null;
  const values = [
    [
      "最终总资产",
      num(summary.final_equity),
      `累计盈亏 ${summary.total_pnl >= 0 ? "+" : ""}${num(summary.total_pnl)}`,
      "",
    ],
    [
      "累计收益率",
      pct(summary.total_return),
      extra == null
        ? labels[state.selected]
        : `较买入持有 ${extra >= 0 ? "+" : ""}${num(extra * 100)} 个百分点`,
      signClass(summary.total_return),
    ],
    [
      "年化收益率",
      pct(summary.cagr),
      `${summary.start} — ${summary.end}`,
      signClass(summary.cagr),
    ],
    [
      "最大回撤",
      pct(summary.max_drawdown),
      `${labels[state.selected]} · 含初始资金`,
      Number(summary.max_drawdown) < 0 ? "negative" : "",
    ],
  ];
  const grid = $("#metrics");
  grid.replaceChildren();
  values.forEach(([label, value, hint, cls], i) => {
    const card = node("article", "metric-card");
    card.append(
      node("span", "", label),
      node("span", "metric-index", `0${i + 1}`),
      node("strong", cls, value),
      node("small", "", hint),
    );
    grid.append(card);
  });
}
function renderComparison() {
  const body = $("#comparison-table tbody");
  body.replaceChildren();
  state.result.comparison.forEach((item) => {
    if (!state.result.results[item.strategy]) return;
    const row = node(
      "tr",
      `strategy-row${item.strategy === state.selected ? " selected" : ""}`,
    );
    const first = node("td");
    const label = node("span", "strategy-cell");
    label.append(
      node("i", `legend-dot ${colorClasses[item.strategy]}`),
      document.createTextNode(labels[item.strategy] || item.strategy),
    );
    first.append(label);
    row.append(first);
    [
      [num(item.final_equity), ""],
      [pct(item.total_return), signClass(item.total_return)],
      [pct(item.cagr), signClass(item.cagr)],
      [pct(item.max_drawdown), Number(item.max_drawdown) < 0 ? "negative" : ""],
      [
        item.extra_return_vs_buy_hold == null
          ? "—"
          : `${item.extra_return_vs_buy_hold >= 0 ? "+" : ""}${num(item.extra_return_vs_buy_hold * 100)} pp`,
        signClass(item.extra_return_vs_buy_hold),
      ],
    ].forEach(([value, cls]) => row.append(node("td", cls, value)));
    row.tabIndex = 0;
    row.setAttribute("aria-label", `查看${labels[item.strategy]}明细`);
    const choose = () => {
      state.selected = item.strategy;
      $("#detail-strategy").value = state.selected;
      renderMetrics();
      renderComparison();
      renderDetails();
    };
    row.addEventListener("click", choose);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter") choose();
    });
    body.append(row);
  });
}
const tableSpecs = {
  trades: [
    ["ticker", "股票"],
    ["entry_date", "买入日期", "date"],
    ["exit_date", "卖出日期", "date"],
    ["quantity", "数量", "num"],
    ["pnl", "盈亏", "signed"],
    ["return", "收益率", "pct"],
    ["status", "状态", "status"],
  ],
  fills: [
    ["date", "成交日期", "date"],
    ["ticker", "股票"],
    ["side", "方向", "side"],
    ["price", "成交价格", "num"],
    ["quantity", "数量", "num"],
    ["fee", "手续费", "num"],
    ["realized_pnl", "已实现盈亏", "signed"],
  ],
  monthly_returns: [
    ["date", "月份", "date"],
    ["ending_equity", "期末资产", "num"],
    ["pnl", "当月盈亏", "signed"],
    ["return", "当月收益率", "pct"],
    ["cumulative_pnl", "累计盈亏", "signed"],
  ],
  yearly_returns: [
    ["date", "年份", "date"],
    ["ending_equity", "期末资产", "num"],
    ["pnl", "当年盈亏", "signed"],
    ["return", "当年收益率", "pct"],
    ["cumulative_pnl", "累计盈亏", "signed"],
  ],
  positions: [
    ["ticker", "股票"],
    ["quantity", "数量", "num"],
    ["valuation_price", "估值价格", "num"],
    ["cost_basis", "持仓成本", "num"],
    ["market_value", "持仓市值", "num"],
    ["unrealized_pnl", "浮动盈亏", "signed"],
  ],
  orders: [
    ["ticker", "股票"],
    ["signal_date", "信号日期", "date"],
    ["execution_date", "执行日期", "date"],
    ["target_weight", "目标权重", "pct"],
    ["filled_quantity", "成交数量", "num"],
    ["status", "状态", "order"],
  ],
};
function renderDetails() {
  const container = $("#detail-table");
  container.replaceChildren();
  const result = state.result?.results[state.selected];
  if (!result) return;
  const summary = result.summary;
  $("#detail-summary").replaceChildren();
  [
    ["现金", num(summary.final_cash)],
    ["已实现盈亏", num(summary.realized_pnl)],
    ["浮动盈亏", num(summary.unrealized_pnl)],
    ["手续费", num(summary.total_fees)],
    ["已平仓胜率", pct(summary.win_rate)],
  ].forEach(([label, value]) => {
    const item = node("span", "", label);
    item.append(node("b", "", value));
    $("#detail-summary").append(item);
  });
  let rows = result.tables[state.table] || [];
  if (["monthly_returns", "yearly_returns"].includes(state.table))
    rows = rows.map((row) => ({
      ...row,
      date: row.date || row.Date || row[Object.keys(row)[0]],
    }));
  const specs = tableSpecs[state.table];
  const table = node("table");
  const head = node("thead");
  const tr = node("tr");
  specs.forEach(([, title]) => tr.append(node("th", "", title)));
  head.append(tr);
  table.append(head);
  const body = node("tbody");
  if (!rows.length) {
    const row = node("tr");
    const cell = node(
      "td",
      "empty-cell",
      state.table === "positions"
        ? "此记录没有持仓文件，较早版本可重新运行以生成。"
        : state.table === "trades"
          ? "本次策略没有交易记录。未触发交易时资金保留为现金。"
          : "暂无记录；较早的命令行结果可能不包含此文件。",
    );
    cell.colSpan = specs.length;
    row.append(cell);
    body.append(row);
  }
  [...rows].reverse().forEach((item) => {
    const row = node("tr");
    specs.forEach(([key, , type]) => {
      let value = item[key],
        cls = "";
      if (key === "ticker" && !value)
        value = state.result.metadata.config.ticker || "—";
      if (type === "date")
        value = value
          ? String(value).slice(
              0,
              state.table === "monthly_returns"
                ? 7
                : state.table === "yearly_returns"
                  ? 4
                  : 10,
            )
          : "—";
      else if (type === "num") value = num(value);
      else if (type === "signed") {
        cls = signClass(value);
        value = num(value);
      } else if (type === "pct") {
        cls = ["return"].includes(key) ? signClass(value) : "";
        value = pct(value);
      } else if (type === "side") {
        cls = value === "buy" ? "positive" : "";
        value = { buy: "买入", sell: "卖出" }[value] || value;
      } else if (type === "status")
        value = { open: "未平仓", closed: "已平仓" }[value] || value;
      else if (type === "order")
        value =
          {
            pending: "待执行",
            filled: "已执行",
            partial: "资金缩减",
            superseded: "已替换",
            no_change: "无需调整",
            insufficient_cash: "现金不足",
          }[value] || value;
      row.append(node("td", cls, value ?? "—"));
    });
    body.append(row);
  });
  table.append(body);
  container.append(table);
  const count = result.counts[state.table] || 0;
  $("#detail-count").textContent =
    `${labels[state.selected]} · ${count > 500 ? `显示最近 500 / ${count}` : `共 ${count}`} 条${state.table === "positions" ? "期末记录" : "记录"}`;
  $("#detail-download").hidden = !rows.length;
  $("#detail-download").href =
    `${API_BASE}/api/runs/${state.result.id}/files/${state.selected}/${state.table}.csv`;
}
function renderLegend() {
  const container = $("#chart-legend");
  container.replaceChildren();
  Object.keys(state.result.results).forEach((name) => {
    const item = node(
      "span",
      `legend-item${state.hidden.has(name) ? " inactive" : ""}`,
    );
    const button = node("button", "", labels[name]);
    button.type = "button";
    button.setAttribute("aria-pressed", String(!state.hidden.has(name)));
    button.addEventListener("click", () => {
      if (state.hidden.has(name)) state.hidden.delete(name);
      else state.hidden.add(name);
      renderLegend();
      renderChart();
    });
    item.append(node("i", `legend-dot ${colorClasses[name]}`), button);
    container.append(item);
  });
}
function svgNode(tag, attrs = {}, text) {
  const element = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([key, value]) =>
    element.setAttribute(key, value),
  );
  if (text != null) element.textContent = text;
  return element;
}
function renderChart() {
  const svg = $("#chart");
  svg.replaceChildren();
  $("#chart-tooltip").hidden = true;
  const W = 900,
    H = 320,
    pad = { l: 66, r: 22, t: 18, b: 35 },
    iw = W - pad.l - pad.r,
    ih = H - pad.t - pad.b;
  const data = state.result
    ? Object.entries(state.result.results)
        .filter(([name]) => !state.hidden.has(name))
        .map(([name, result]) => ({
          name,
          points: result.curve.filter(
            (point) => point[state.chartMode] != null,
          ),
        }))
    : [];
  const all = data.flatMap((series) => series.points);
  const latest = all.length
    ? Math.max(...all.map((point) => new Date(point.date).getTime()))
    : 1;
  let earliest = all.length
    ? Math.min(...all.map((point) => new Date(point.date).getTime()))
    : 0;
  if (state.months) {
    const limit = new Date(latest);
    limit.setUTCMonth(limit.getUTCMonth() - state.months);
    earliest = Math.max(earliest, limit.getTime());
    data.forEach((series) => {
      series.points = series.points.filter(
        (point) => new Date(point.date).getTime() >= earliest,
      );
    });
  }
  const values = data.flatMap((series) =>
    series.points.map(
      (point) =>
        point[state.chartMode] * (state.chartMode === "equity" ? 1 : 100),
    ),
  );
  let min = values.length
    ? Math.min(...values, state.chartMode === "equity" ? Infinity : 0)
    : -10;
  let max = values.length
    ? Math.max(...values, state.chartMode === "equity" ? -Infinity : 0)
    : 30;
  const buffer = Math.max(
    (max - min) * 0.14,
    state.chartMode === "equity" ? 1 : 1,
  );
  min -= buffer;
  max += buffer;
  const x = (date) =>
    pad.l +
    ((new Date(date).getTime() - earliest) / Math.max(1, latest - earliest)) *
      iw;
  const y = (value) => pad.t + ((max - value) / (max - min)) * ih;
  for (let i = 0; i <= 4; i++) {
    const yy = pad.t + (ih * i) / 4,
      value = max - ((max - min) * i) / 4;
    svg.append(
      svgNode("line", {
        x1: pad.l,
        x2: W - pad.r,
        y1: yy,
        y2: yy,
        stroke: "#eaf0ed",
        "stroke-width": 1,
        "stroke-dasharray": "3 4",
      }),
    );
    let label =
      state.chartMode === "equity"
        ? Math.abs(value) >= 10000
          ? `${num(value / 10000, 1)}万`
          : num(value, 0)
        : `${num(value, 1)}%`;
    svg.append(
      svgNode(
        "text",
        {
          x: pad.l - 13,
          y: yy + 4,
          "text-anchor": "end",
          fill: "#a4b0b6",
          "font-size": 10,
        },
        label,
      ),
    );
  }
  if (all.length) {
    for (let i = 0; i <= 4; i++) {
      const time = earliest + ((latest - earliest) * i) / 4;
      const date = new Date(time);
      svg.append(
        svgNode(
          "text",
          {
            x: pad.l + (iw * i) / 4,
            y: H - 10,
            "text-anchor": "middle",
            fill: "#a4b0b6",
            "font-size": 10,
          },
          `${date.getUTCFullYear()}.${String(date.getUTCMonth() + 1).padStart(2, "0")}`,
        ),
      );
    }
    data.forEach((series) => {
      const path = series.points
        .map(
          (point, i) =>
            `${i ? "L" : "M"}${x(point.date).toFixed(2)},${y(point[state.chartMode] * (state.chartMode === "equity" ? 1 : 100)).toFixed(2)}`,
        )
        .join(" ");
      if (series.points.length)
        svg.append(
          svgNode("path", {
            d: path,
            stroke: colors[series.name],
            "stroke-width": 2,
            fill: "none",
            "stroke-linejoin": "round",
            "stroke-linecap": "round",
          }),
        );
    });
  }
  $("#chart-empty").hidden = !!state.result;
  if (!values.length && state.result) {
    svg.append(
      svgNode(
        "text",
        {
          x: W / 2,
          y: H / 2,
          "text-anchor": "middle",
          fill: "#96a59b",
          "font-size": 12,
        },
        "点击图例显示策略曲线",
      ),
    );
    return;
  }
  const guide = svgNode("line", {
    x1: 0,
    x2: 0,
    y1: pad.t,
    y2: H - pad.b,
    stroke: "#b5c6bb",
    "stroke-width": 1,
    "stroke-dasharray": "3 3",
    visibility: "hidden",
  });
  svg.append(guide);
  const hit = svgNode("rect", {
    x: pad.l,
    y: pad.t,
    width: iw,
    height: ih,
    fill: "transparent",
  });
  svg.append(hit);
  hit.addEventListener("pointermove", (event) => {
    if (!all.length) return;
    const rect = svg.getBoundingClientRect();
    const cursorX = ((event.clientX - rect.left) / rect.width) * W;
    const time = earliest + ((cursorX - pad.l) / iw) * (latest - earliest);
    const tooltip = $("#chart-tooltip");
    tooltip.replaceChildren();
    let chosenDate = "";
    const points = [];
    data.forEach((series) => {
      if (!series.points.length) return;
      let lo = 0,
        hi = series.points.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (new Date(series.points[mid].date).getTime() < time) lo = mid + 1;
        else hi = mid;
      }
      const point =
        lo > 0 &&
        Math.abs(new Date(series.points[lo - 1].date).getTime() - time) <
          Math.abs(new Date(series.points[lo].date).getTime() - time)
          ? series.points[lo - 1]
          : series.points[lo];
      chosenDate ||= point.date;
      points.push([series.name, point]);
    });
    tooltip.append(node("strong", "", String(chosenDate).slice(0, 10)));
    points.forEach(([name, point]) => {
      const row = node("div", "tooltip-row");
      row.append(
        node("i", `legend-dot ${colorClasses[name]}`),
        node("span", "", labels[name]),
        node(
          "b",
          "",
          state.chartMode === "equity"
            ? num(point.equity)
            : pct(point[state.chartMode]),
        ),
      );
      tooltip.append(row);
    });
    guide.setAttribute("x1", cursorX);
    guide.setAttribute("x2", cursorX);
    guide.setAttribute("visibility", "visible");
    tooltip.hidden = false;
    const wrap = $("#chart-wrap").getBoundingClientRect();
    tooltip.style.left = `${Math.min(Math.max(8, event.clientX - wrap.left + 16), Math.max(8, wrap.width - tooltip.offsetWidth - 8))}px`;
    tooltip.style.top = `${Math.max(tooltip.offsetHeight + 12, event.clientY - wrap.top - 12)}px`;
  });
  hit.addEventListener("pointerleave", () => {
    guide.setAttribute("visibility", "hidden");
    $("#chart-tooltip").hidden = true;
  });
}
function setBusy(busy) {
  state.running = busy;
  $("#run-button").disabled = busy;
  $("#run-button span").textContent = busy ? "正在回测…" : "运行回测";
  $("#job-progress").hidden = !busy;
}
async function startRun(event) {
  event.preventDefault();
  if (state.running) return;
  showError("", "#form-error");
  showError("");
  const data = formData();
  try {
    if (!data.strategies.length) throw new Error("请至少选择一种策略。");
    if (
      !data.pool.length ||
      data.pool.some(
        (stock) =>
          !stock.ticker || !Number.isFinite(stock.weight) || stock.weight < 0,
      )
    )
      throw new Error("请补全股票代码和有效权重。");
    if (
      new Set(data.pool.map((stock) => stock.ticker)).size !== data.pool.length
    )
      throw new Error("股票池中有重复代码，请移除重复项。");
    if (data.pool.reduce((sum, stock) => sum + stock.weight, 0) > 1 + 1e-12)
      throw new Error("股票权重合计不能超过 100%。");
    setBusy(true);
    state.changedWhileRunning = false;
    $("#job-message").textContent = "正在提交回测…";
    $("#progress-bar").value = 0;
    $("#job-percent").textContent = "0%";
    const job = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify(data),
    });
    saveDraft();
    beginPolling(job.id);
  } catch (error) {
    setBusy(false);
    showError(error.message, "#form-error");
  }
}
async function beginPolling(id) {
  if (state.activeJob === id && state.busyPoll) return;
  state.activeJob = id;
  state.busyPoll = true;
  setBusy(true);
  try {
    localStorage.setItem("f-analysis.active-job", JSON.stringify(id));
  } catch {
    /* 可不持久化 */
  }
  async function poll() {
    if (state.activeJob !== id) return;
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      $("#job-message").textContent = job.message || stateLabels[job.state];
      $("#job-percent").textContent = `${job.progress || 0}%`;
      $("#progress-bar").value = job.progress || 0;
      if (job.state === "succeeded") {
        setBusy(false);
        state.activeJob = null;
        state.busyPoll = false;
        try {
          localStorage.removeItem("f-analysis.active-job");
        } catch {
          /* 可不持久化 */
        }
        await loadRun(id, !state.changedWhileRunning);
        await refreshRuns();
        await refreshCache();
        toast("回测完成，结果已保存到本机");
      } else if (["failed", "interrupted"].includes(job.state)) {
        setBusy(false);
        state.activeJob = null;
        state.busyPoll = false;
        try {
          localStorage.removeItem("f-analysis.active-job");
        } catch {
          /* 可不持久化 */
        }
        showError(`回测未完成：${job.message}`);
        $("#result-status").textContent = state.result
          ? "运行失败 · 当前仍显示上一次结果"
          : "回测未完成";
        await refreshRuns();
      } else {
        setTimeout(poll, 1000);
      }
    } catch (error) {
      setBusy(false);
      state.busyPoll = false;
      state.activeJob = null;
      showError(`无法读取运行状态：${error.message}。刷新页面可重新连接。`);
    }
  }
  poll();
}
function resetForm() {
  applyConfig(state.config.defaults);
  changed();
  showError("");
  showError("", "#form-error");
  navigate("workspace");
  toast("已恢复默认配置，可以开始新的回测");
}
$$("[data-view]").forEach((button) =>
  button.addEventListener("click", () => navigate(button.dataset.view)),
);
$("#new-run").addEventListener("click", () => {
  if (state.config) resetForm();
});
$("#add-stock").addEventListener("click", () => {
  if ($$(".pool-row").length >= 50) return toast("股票池最多支持 50 只股票");
  addStock({}, true);
  changed();
});
$("#equal-weights").addEventListener("click", () => {
  const rows = $$(".pool-row"); // 向下取整避免浮点权重超过 100%
  rows.forEach((row) => {
    $(".stock-weight", row).value =
      Math.floor(100000000 / rows.length) / 1000000;
  });
  changed();
});
$$("[data-ma]").forEach((button) =>
  button.addEventListener("click", () => {
    $("#ma-window").value = button.dataset.ma;
    changed();
  }),
);
$("#backtest-form").addEventListener("submit", startRun);
$("#backtest-form").addEventListener("input", (event) => {
  if (!event.target.closest(".pool-row")) changed();
});
$("#backtest-form").addEventListener("change", (event) => {
  if (!event.target.closest(".pool-row")) changed();
});
function renderPoolPresets(selected = "") {
  $("#pool-preset").replaceChildren();
  addOption($("#pool-preset"), "选择股票池模板", "");
  state.config.presets.forEach((item) => addOption(
    $("#pool-preset"),
    item.saved ? `已保存：${item.name}` : item.name === "example" ? "示例：银行 / 汽车 / 红利" : item.name,
    item.name,
  ));
  $("#pool-preset").value = selected;
}
$("#pool-preset").addEventListener("change", () => {
  const preset = state.config?.presets.find(
    (item) => item.name === $("#pool-preset").value,
  );
  if (preset) {
    const entries = Object.entries(preset.stocks || {});
    const pool = preset.pool || entries.map(([ticker, name]) => ({
      ticker, name, weight: Math.floor(100000000 / entries.length) / 100000000,
    }));
    $("#pool-rows").replaceChildren();
    pool.forEach((stock) => addStock(stock));
    $("#pool-name").value = preset.saved ? preset.name : "";
    changed();
    toast("已载入股票池及权重，策略参数保持不变");
  }
});
$("#new-pool").addEventListener("click", () => {
  if (!confirm("新建将清空当前编辑的股票池，尚未保存的内容将丢失。是否继续？")) return;
  $("#pool-rows").replaceChildren();
  addStock({ weight: 1 }, true);
  $("#pool-name").value = "";
  $("#pool-preset").value = "";
  changed();
});
$("#save-pool").addEventListener("click", async () => {
  if (!state.config) return toast("请等待本机服务连接后再保存");
  const name = $("#pool-name").value.trim();
  if (!name) { $("#pool-name").focus(); return toast("请填写股票池名称"); }
  if (!$$(".pool-row input").every((input) => input.reportValidity())) return;
  const exists = state.config.presets.some((item) => item.saved && item.name === name);
  if (exists && !confirm(`股票池「${name}」已存在，是否覆盖保存？`)) return;
  const button = $("#save-pool");
  const pool = formData().pool;
  button.disabled = true;
  button.textContent = "保存中…";
  try {
    const result = await api("/api/pools", {
      method: "POST", body: JSON.stringify({name, pool, overwrite: exists}),
    });
    state.config.presets = result.presets;
    renderPoolPresets(result.name);
    $("#pool-name").value = result.name;
    toast("股票池已保存到本机，下次可从快速载入中选择");
  } catch (error) {
    toast(`保存失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "保存股票池";
  }
});
$("#reuse-button").addEventListener("click", () => {
  if (state.result) {
    applyConfig(state.result.metadata.config);
    state.dirty = false;
    $("#dirty-banner").hidden = true;
    $("#reuse-button").hidden = true;
    saveDraft();
    toast("已恢复当前结果使用的参数");
  }
});
$("#detail-strategy").addEventListener("change", () => {
  state.selected = $("#detail-strategy").value;
  renderMetrics();
  renderComparison();
  renderDetails();
});
$$("#detail-tabs button").forEach((button) =>
  button.addEventListener("click", () => {
    state.table = button.dataset.table;
    $$("#detail-tabs button").forEach((item) =>
      item.classList.toggle("active", item === button),
    );
    renderDetails();
  }),
);
$$("#chart-mode button").forEach((button) =>
  button.addEventListener("click", () => {
    state.chartMode = button.dataset.mode;
    $$("#chart-mode button").forEach((item) =>
      item.classList.toggle("active", item === button),
    );
    renderChart();
  }),
);
$$("#chart-period button").forEach((button) =>
  button.addEventListener("click", () => {
    state.months = Number(button.dataset.months);
    $$("#chart-period button").forEach((item) =>
      item.classList.toggle("active", item === button),
    );
    renderChart();
  }),
);
$("#refresh-history").addEventListener("click", () =>
  refreshRuns().catch((error) => showError(error.message)),
);
$("#refresh-cache").addEventListener("click", () =>
  refreshCache().catch((error) => showError(error.message)),
);
$("#help-button").addEventListener("click", () =>
  $("#help-dialog").showModal(),
);
$("#close-help").addEventListener("click", () => $("#help-dialog").close());
$("#help-done").addEventListener("click", () => $("#help-dialog").close());
async function boot() {
  renderChart();
  try {
    state.config = await api("/api/config");
    state.token = state.config.token;
    $("#connection-text").textContent = "本机引擎已连接";
    const draft = readStorage("f-analysis.draft.v1");
    applyConfig(draft?.pool?.length ? draft : state.config.defaults);
    renderPoolPresets();
    await refreshRuns();
    const last = state.runs.find((run) => run.state === "succeeded");
    if (last) {
      try {
        await loadRun(last.id, !draft);
      } catch (error) {
        showError(`历史结果读取失败：${error.message}`);
      }
    }
    await refreshCache();
    const activeJob = readStorage("f-analysis.active-job");
    if (activeJob) beginPolling(activeJob);
    const view = location.hash.slice(1);
    if (["history", "cache"].includes(view)) navigate(view);
  } catch (error) {
    $("#connection-text").textContent = "本机服务未连接";
    $("#connection").classList.add("offline");
    showError(
      `连接失败：${error.message}。请确认终端中的网页服务仍在运行，然后刷新页面。`,
    );
  }
}
boot();

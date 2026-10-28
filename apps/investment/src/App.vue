<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { API_BASE } from "./api";
import { stateLabels } from "./model";
import { useInvestment } from "./useInvestment";
import BacktestForm from "./components/BacktestForm.vue";
import BacktestResults from "./components/BacktestResults.vue";
import ResultTable from "./components/ResultTable.vue";
const {
  config,
  service,
  result,
  runs,
  cache,
  error,
  connected,
  running,
  job,
  status,
  dirty,
  refreshRuns,
  refreshCache,
  loadRun,
  restore,
  startRun,
  reset,
  savePool,
  loadPreset,
  guard,
} = useInvestment();
const view = ref("workspace"),
  help = ref<HTMLDialogElement>();
const views: Record<string, string> = {
  workspace: "策略回测",
  history: "历史记录",
  cache: "行情缓存",
};
function addCached(ticker: string) {
  if (
    !config.value.pool.some(
      (s) => s.ticker.toUpperCase() === ticker.toUpperCase(),
    ) &&
    config.value.pool.length < 50
  ) {
    config.value.pool.push({ ticker, name: ticker, weight: 0 });
    navigate("workspace");
  }
}
function hashChange() {
  view.value = ["history", "cache"].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : "workspace";
}
function navigate(key: string) {
  view.value = key;
  location.hash = key;
  if (key === "history") void guard(refreshRuns);
  if (key === "cache") void guard(refreshCache);
}
onMounted(() => {
  hashChange();
  window.addEventListener("hashchange", hashChange);
});
onUnmounted(() => window.removeEventListener("hashchange", hashChange));
async function openRun(id: string) {
  await guard(async () => {
    await loadRun(id);
    navigate("workspace");
  });
}
async function save(name: string) {
  await guard(async () => {
    await savePool(name);
    status.value = "股票池已保存到本机";
  });
}
</script>
<template>
  <div class="sm-container">
    <header class="sm-header">
      <div class="sm-brand">
        <span class="sm-mark">s.</span>Self Manager
        <span class="muted">/ 投资研究</span>
      </div>
      <a href="/" class="sm-back">← 返回主页</a>
    </header>
    <div class="sm-intro">
      <p class="sm-eyebrow">INVESTMENT RESEARCH</p>
      <h1 class="sm-title">从想法出发，让数据回答。</h1>
      <p class="sm-description">
        配置股票池、比较策略表现，积累可复现的投资研究。
      </p>
    </div>
    <div class="section-heading">
      <nav class="page-nav" aria-label="投资研究导航">
        <button
          v-for="(label, key) in views"
          :key="key"
          class="sm-button"
          :class="{ 'sm-button-primary': view === key }"
          :data-view="key"
          :aria-current="view === key ? 'page' : undefined"
          @click="navigate(key)"
        >
          {{ label }}
        </button>
      </nav>
      <span id="connection-text" class="muted">{{
        connected ? "本机引擎已连接" : "连接本机服务…"
      }}</span>
    </div>
    <div class="section-heading">
      <h2 id="page-title">{{ views[view] }}</h2>
      <div class="actions">
        <button id="help-button" class="text-button" @click="help?.showModal()">
          使用说明</button
        ><button
          id="new-run"
          class="sm-button"
          :disabled="!connected"
          @click="
            reset();
            navigate('workspace');
          "
        >
          ＋ 新建回测
        </button>
      </div>
    </div>
    <div v-if="error" id="global-error" class="notice error" role="alert">
      {{ error }}
    </div>
    <section
      v-show="view === 'workspace'"
      id="workspace-view"
      class="workspace-grid"
    >
      <aside class="sm-panel config-panel">
        <h2>回测配置</h2>
        <BacktestForm
          v-model="config"
          :running="running || !connected"
          :presets="service?.presets || []"
          @submit="startRun"
          @save-pool="save"
          @preset="loadPreset"
        />
      </aside>
      <div class="result-column">
        <div v-if="running" id="job-progress" class="sm-panel">
          <strong id="job-message">{{ job?.message || "正在提交回测…" }}</strong
          ><span id="job-percent"> {{ job?.progress || 0 }}%</span
          ><progress id="progress-bar" max="100" :value="job?.progress || 0" />
          <p class="muted">可切换页面查看记录，回测将在后台继续运行。</p>
        </div>
        <BacktestResults
          :result="result"
          :dirty="dirty"
          :status="status"
          @restore="restore"
        />
      </div>
    </section>
    <section v-if="view === 'history'" id="history-view" class="sm-panel">
      <div class="section-heading">
        <h2>
          运行记录 <small id="history-count">{{ runs.length }}</small>
        </h2>
        <button
          id="refresh-history"
          class="sm-button"
          @click="guard(refreshRuns)"
        >
          刷新记录
        </button>
      </div>
      <p class="muted">
        网页与命令行生成的结果统一保存在本机，选择记录可恢复参数并查看报告。
      </p>
      <div id="history-list">
        <article v-for="run in runs" :key="run.id" class="history-row">
          <div>
            <strong>{{ run.id }}</strong
            ><small
              >{{ run.created_at }} ·
              {{ stateLabels[run.state] || run.state }} ·
              {{ run.message }}</small
            >
          </div>
          <div class="actions">
            <button
              v-if="run.state === 'succeeded'"
              class="sm-button"
              :data-run="run.id"
              @click="openRun(run.id)"
            >
              查看结果</button
            ><a
              v-if="run.state === 'succeeded'"
              class="text-button"
              :href="`${API_BASE}/api/runs/${encodeURIComponent(run.id)}/download.zip`"
              >导出 ZIP</a
            >
          </div>
        </article>
        <p v-if="!runs.length" class="empty">暂无运行记录</p>
      </div>
    </section>
    <section v-if="view === 'cache'" id="cache-view" class="sm-panel">
      <div class="section-heading">
        <h2>
          行情缓存 <small id="cache-total">{{ cache.length }} 个标的</small>
        </h2>
        <button
          id="refresh-cache"
          class="sm-button"
          @click="guard(refreshCache)"
        >
          刷新列表
        </button>
      </div>
      <p class="muted">
        缓存不会自动更新。需要最新行情时，请在回测配置中选择“重新下载并更新缓存”。
      </p>
      <div class="actions cache-actions">
        <button
          v-for="c in cache"
          :key="c.ticker"
          class="sm-button"
          :disabled="
            config.pool.some(
              (s) => s.ticker.toUpperCase() === c.ticker.toUpperCase(),
            ) || config.pool.length >= 50
          "
          @click="addCached(c.ticker)"
        >
          ＋ {{ c.ticker }} 加入股票池
        </button>
      </div>
      <ResultTable
        id="cache-table"
        :rows="cache.map((c) => ({ ...c }))"
        :columns="[
          ['ticker', '股票代码'],
          ['start_date', '行情起始'],
          ['end_date', '行情截止'],
          ['row_count', '价格点数'],
          ['fetched_at', '缓存更新时间'],
        ]"
      />
    </section>
    <footer class="sm-footer">
      本机数据 · 本机计算 · 每一笔交易都有完整记录。
    </footer>
  </div>
  <dialog id="help-dialog" ref="help">
    <div class="section-heading">
      <h2>让研究更简单</h2>
      <button
        id="close-help"
        class="sm-button"
        aria-label="关闭说明"
        @click="help?.close()"
      >
        ×
      </button>
    </div>
    <ol>
      <li>
        配置股票池：使用 Yahoo 代码，上海为 .SS、深圳为 .SZ，权重合计不超过
        100%。
      </li>
      <li>选择策略：可同时比较买入持有、均线、固定权重、动量与定投策略。</li>
      <li>运行回测：结果自动保存，可在历史记录中重新打开或导出。</li>
    </ol>
    <p>缓存不会自动更新。离线模式仅读取缓存，刷新模式重新下载完整历史。</p>
    <button
      id="help-done"
      class="sm-button sm-button-primary"
      @click="help?.close()"
    >
      开始研究
    </button>
  </dialog>
</template>

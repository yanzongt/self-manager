import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { createApi } from "./api";
import {
  checkCapabilities,
  clone,
  normalizeConfig,
  requestConfig,
  validatePool,
  type BacktestConfig,
  type CacheEntry,
  type Job,
  type Run,
  type RunDetails,
  type ServiceConfig,
} from "./model";
const DRAFT = "f-analysis.draft.v1",
  ACTIVE = "f-analysis.active-job";
function read<T>(key: string): T | null {
  try {
    return JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}
function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Draft persistence is optional; server-side results remain available. */
  }
}
export function useInvestment() {
  const config = ref(normalizeConfig()),
    service = ref<ServiceConfig>(),
    result = ref<RunDetails>(),
    runs = ref<Run[]>([]),
    cache = ref<CacheEntry[]>([]),
    error = ref(""),
    connected = ref(false),
    running = ref(false),
    job = ref<Job>(),
    status = ref("准备开始");
  const api = createApi(() => service.value?.token || "");
  let timer: ReturnType<typeof setTimeout> | undefined,
    disposed = false,
    loadSerial = 0;
  const signature = ref(""),
    dirty = computed(
      () =>
        !!result.value &&
        JSON.stringify(requestConfig(config.value)) !== signature.value,
    );
  watch(config, () => write(DRAFT, requestConfig(config.value)), {
    deep: true,
  });
  async function refreshRuns() {
    runs.value = (await api<{ items: Run[] }>("/api/runs")).items;
  }
  async function refreshCache() {
    cache.value = (await api<{ items: CacheEntry[] }>("/api/cache")).items;
  }
  async function loadRun(id: string, reuse = true) {
    const serial = ++loadSerial;
    status.value = "正在读取结果…";
    const value = await api<RunDetails>("/api/runs/" + encodeURIComponent(id));
    if (disposed || serial !== loadSerial) return;
    result.value = value;
    signature.value = JSON.stringify(
      requestConfig(normalizeConfig(value.metadata.config)),
    );
    if (reuse) config.value = normalizeConfig(value.metadata.config);
    status.value = "已完成";
  }
  function restore() {
    if (result.value)
      config.value = normalizeConfig(result.value.metadata.config);
  }
  async function poll(id: string, submittedSignature?: string) {
    running.value = true;
    write(ACTIVE, id);
    try {
      const value = await api<Job>("/api/jobs/" + encodeURIComponent(id));
      if (disposed) return;
      job.value = value;
      if (["succeeded", "failed", "interrupted"].includes(value.state)) {
        running.value = false;
        write(ACTIVE, null);
        if (value.state === "succeeded") {
          await loadRun(
            id,
            !!submittedSignature &&
              JSON.stringify(requestConfig(config.value)) ===
                submittedSignature,
          );
          status.value = "已完成，结果已保存到本机";
        } else {
          error.value = "回测未完成：" + (value.message || value.state);
          status.value = result.value
            ? "运行失败 · 当前显示上一次结果"
            : "回测未完成";
        }
        await Promise.all([refreshRuns(), refreshCache()]);
      } else timer = setTimeout(() => void poll(id, submittedSignature), 1000);
    } catch (e) {
      running.value = false;
      error.value =
        "无法读取运行状态：" + (e as Error).message + "。刷新页面可重新连接。";
    }
  }
  async function startRun() {
    if (running.value) return;
    error.value = "";
    try {
      const payload = requestConfig(config.value);
      validatePool(payload.pool);
      if (!payload.strategies.length) throw Error("请至少选择一种策略");
      running.value = true;
      service.value = await api<ServiceConfig>("/api/config");
      checkCapabilities(payload, service.value.capabilities);
      const next = await api<Job>("/api/runs", payload);
      await poll(next.id, JSON.stringify(payload));
    } catch (e) {
      running.value = false;
      error.value = (e as Error).message;
    }
  }
  function reset() {
    config.value = normalizeConfig(service.value?.defaults);
    error.value = "";
  }
  async function savePool(name: string) {
    name = name.trim();
    if (!name) throw Error("请填写股票池名称");
    const pool = requestConfig(config.value).pool;
    validatePool(pool);
    const exists = service.value?.presets.some(
      (p) => p.saved && p.name === name,
    );
    if (exists && !confirm(`股票池「${name}」已存在，是否覆盖保存？`)) return;
    const value = await api<{ presets: ServiceConfig["presets"] }>(
      "/api/pools",
      { name, pool, overwrite: !!exists },
    );
    if (service.value) service.value.presets = value.presets;
  }
  function loadPreset(name: string) {
    const preset = service.value?.presets.find((p) => p.name === name);
    if (preset)
      config.value.pool = clone(
        preset.pool ||
          Object.entries(preset.stocks || {}).map(([ticker, name], _, a) => ({
            ticker,
            name,
            weight: Math.floor(1e8 / a.length) / 1e8,
          })),
      );
  }
  async function guard(action: () => Promise<unknown>) {
    try {
      await action();
    } catch (e) {
      error.value = (e as Error).message;
    }
  }
  onMounted(async () => {
    try {
      const draft = read<BacktestConfig>(DRAFT);
      service.value = await api<ServiceConfig>("/api/config");
      connected.value = true;
      config.value = normalizeConfig(
        draft?.pool?.length ? draft : service.value.defaults,
      );
      await refreshRuns();
      const last = runs.value.find((r) => r.state === "succeeded");
      if (last) await guard(() => loadRun(last.id, !draft));
      await refreshCache();
      const active = read<string>(ACTIVE);
      if (active) void poll(active);
    } catch (e) {
      error.value =
        "连接失败：" + (e as Error).message + "。请确认本机服务仍在运行。";
    }
  });
  onUnmounted(() => {
    disposed = true;
    loadSerial++;
    clearTimeout(timer);
  });
  return {
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
  };
}

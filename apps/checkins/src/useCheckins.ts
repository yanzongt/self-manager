import { onMounted, ref } from "vue";
import { loadCheckins, saveCheckins } from "./api";
import type { Data, Item, ItemType } from "./model";

export function useCheckins() {
  const state = ref<Data>({ items: [] });
  const revision = ref<string | null>(null);
  const ready = ref(false);
  const busy = ref(false);
  const message = ref("正在读取本机记录…");
  const error = ref(false);

  function status(text: string, isError = false) {
    message.value = text;
    error.value = isError;
  }

  async function load() {
    try {
      const saved = await loadCheckins();
      state.value = saved.data || { items: [] };
      revision.value = saved.revision;
      ready.value = true;
      status("已连接本机存储 · 每次打卡自动保存");
    } catch (e) {
      status(`读取失败：${(e as Error).message}。请刷新重试。`, true);
    }
  }

  async function mutate(change: (data: Data) => void) {
    if (busy.value || !ready.value) return;
    busy.value = true;
    const next = JSON.parse(JSON.stringify(state.value)) as Data;
    try {
      change(next);
      const saved = await saveCheckins(next, revision.value);
      state.value = next;
      revision.value = saved.revision;
      status("已保存 · " + new Date().toLocaleTimeString("zh-CN"));
    } catch (e) {
      ready.value = false;
      status(
        `保存失败：${(e as Error).message}。本次操作未确认，请刷新读取最新记录后重试。`,
        true,
      );
    } finally {
      busy.value = false;
    }
  }

  function addItem(name: string, type: ItemType) {
    return mutate((data) =>
      data.items.push({
        id: crypto.randomUUID(),
        name,
        type,
        records: [],
        activeSince: null,
      }),
    );
  }

  function check(item: Item) {
    return mutate((data) => {
      const current = data.items.find((candidate) => candidate.id === item.id)!;
      const now = Date.now();
      if (current.type === "count") current.records.push({ start: now });
      else if (current.activeSince == null) current.activeSince = now;
      else {
        if (now < current.activeSince)
          throw new Error("系统时间早于开始时间，请校准时间后重试");
        current.records.push({ start: current.activeSince, end: now });
        current.activeSince = null;
      }
    });
  }

  onMounted(load);
  return { state, ready, busy, message, error, addItem, check };
}

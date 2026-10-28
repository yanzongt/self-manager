export type ItemType = "count" | "timer";
export interface RecordEntry {
  start: number;
  end?: number;
}
export interface Item {
  id: string;
  name: string;
  type: ItemType;
  records: RecordEntry[];
  activeSince?: number | null;
}
export interface Data {
  items: Item[];
}
export const localDay = (t: number | Date) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const duration = (ms: number) => {
  const s = Math.floor(Math.max(0, ms) / 1000),
    h = Math.floor(s / 3600),
    m = Math.floor((s % 3600) / 60);
  return h ? `${h}小时 ${m}分` : `${m}分 ${s % 60}秒`;
};
export const clock = (ms: number) => {
  const s = Math.floor(Math.max(0, ms) / 1000);
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
};
export const timestamp = (t: number) =>
  new Date(t).toLocaleString("zh-CN", { hour12: false });
export function daily(items: Item[], now = Date.now()) {
  const counts: Record<string, number> = {},
    times: Record<string, number> = {};
  for (const item of items) {
    if (item.type === "count") {
      for (const r of item.records) {
        const key = localDay(r.start);
        counts[key] = (counts[key] || 0) + 1;
      }
      continue;
    }
    const sessions = [...item.records];
    if (item.activeSince != null)
      sessions.push({ start: item.activeSince, end: now });
    for (const r of sessions) {
      let start = r.start;
      const finish = r.end ?? start;
      while (start < finish) {
        const d = new Date(start);
        d.setHours(24, 0, 0, 0);
        const end = Math.min(finish, d.getTime()),
          key = localDay(start);
        times[key] = (times[key] || 0) + end - start;
        start = end;
      }
    }
  }
  return { counts, times };
}

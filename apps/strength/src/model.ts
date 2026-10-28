import { DEFAULT_EX, DEFAULT_ROUTINES } from "./defaults";

export interface Exercise {
  id: string;
  name: string;
  part: string;
  note: string;
  guide: string;
  sets: number;
  reps: number;
  weight: number;
  unit: string;
}
export interface Routine {
  title: string;
  purpose: string;
  ids: string[];
}
export interface TrainingLog {
  id: string;
  date: string;
  exId: string;
  sets: number;
  reps: number;
  weight: number;
  unit: string;
  pain: number;
  note: string;
}
export const bodyFields = {
  weight: "体重",
  chest: "胸围",
  arm: "臂围",
  waist: "腰围",
  hip: "臀围",
  thigh: "大腿围",
};
export type BodyMetric = keyof typeof bodyFields;
export type Measurement = { id: string; date: string; note: string } & Record<
  BodyMetric,
  number | null
>;
export interface Plan {
  exercises: Exercise[];
  routines: Record<number, Routine>;
}
export interface StrengthData extends Plan {
  logs: TrainingLog[];
  body: Measurement[];
  weights: Record<string, number>;
}
export type FileType = "plan" | "records" | "backup";
export const STORAGE_KEY = "strengthTracker_v1";
export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
export const uid = () => crypto.randomUUID();
export const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const byDate = (
  a: { date: string; id: string },
  b: { date: string; id: string },
) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id);
export const validDate = (v: unknown): v is string =>
  typeof v === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  new Date(v + "T12:00:00Z").toISOString().slice(0, 10) === v;
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw Error("数据格式无效");
  return value as Record<string, unknown>;
}
function list(value: unknown): unknown[] {
  if (!Array.isArray(value) || value.length > 50000) throw Error("列表无效");
  return value;
}
function text(v: unknown, max = 2000, required = false): string {
  if (typeof v !== "string" || v.length > max || (required && !v.trim()))
    throw Error("文本字段无效");
  return v;
}
function number(v: unknown, min: number, max: number, integer = false): number {
  if (
    typeof v !== "number" ||
    !Number.isFinite(v) ||
    v < min ||
    v > max ||
    (integer && !Number.isInteger(v))
  )
    throw Error("训练或测量数值无效");
  return v;
}
function identity(x: Record<string, unknown>, ids: Set<string>) {
  const id = text(x.id, 100, true);
  if (!/^[a-zA-Z0-9_-]+$/.test(id) || ids.has(id))
    throw Error("编号无效或重复");
  ids.add(id);
  return id;
}
function unit(v: unknown) {
  if (v !== "次" && v !== "秒") throw Error("数量单位无效");
  return v;
}
export function validateExercises(raw: unknown): Exercise[] {
  const rows = list(raw),
    ids = new Set<string>();
  if (!rows.length || rows.length > 1000) throw Error("动作列表无效");
  return rows.map((v) => {
    const x = record(v);
    return {
      id: identity(x, ids),
      name: text(x.name, 100, true),
      part: text(x.part, 100, true),
      note: text(x.note),
      guide: text(x.guide ?? "", 10000),
      sets: number(x.sets, 1, 30, true),
      reps: number(x.reps, 1, 500, true),
      weight: number(x.weight, 0, 1000),
      unit: unit(x.unit),
    };
  });
}
export function validatePlan(raw: unknown): Plan {
  const x = record(raw),
    exercises = validateExercises(x.exercises),
    days = record(x.routines),
    routines: Plan["routines"] = {},
    ids = new Set(exercises.map((e) => e.id));
  for (let day = 0; day < 7; day++) {
    const r = record(days[day]),
      items = list(r.ids).map((v) => text(v, 100, true));
    if (
      new Set(items).size !== items.length ||
      items.some((id) => !ids.has(id))
    )
      throw Error("每周安排存在无效动作");
    routines[day] = {
      title: text(r.title, 200, true),
      purpose: text(r.purpose),
      ids: items,
    };
  }
  return { exercises, routines };
}
export function validateLogs(
  raw: unknown,
  exercises: Exercise[],
): TrainingLog[] {
  const ids = new Set<string>();
  return list(raw).map((v) => {
    const x = record(v);
    if (!validDate(x.date) || !exercises.some((e) => e.id === x.exId))
      throw Error("训练记录日期或动作无效");
    return {
      id: identity(x, ids),
      date: x.date,
      exId: text(x.exId, 100, true),
      sets: number(x.sets, 1, 30, true),
      reps: number(x.reps, 1, 500, true),
      weight: number(x.weight, 0, 1000),
      unit: unit(x.unit ?? "次"),
      pain: number(x.pain, 0, 10, true),
      note: text(x.note ?? ""),
    };
  });
}
export function validateBody(raw: unknown): Measurement[] {
  const ids = new Set<string>();
  return list(raw).map((v) => {
    const x = record(v);
    if (!validDate(x.date)) throw Error("身体测量日期无效");
    const fields = Object.fromEntries(
      Object.keys(bodyFields).map((k) => [
        k,
        x[k] == null ? null : number(x[k], 0.01, 500),
      ]),
    ) as Record<BodyMetric, number | null>;
    if (Object.values(fields).every((v) => v === null))
      throw Error("身体测量记录为空");
    return {
      id: identity(x, ids),
      date: x.date,
      note: text(x.note ?? ""),
      ...fields,
    };
  });
}
export function emptyData(): StrengthData {
  return {
    exercises: clone(DEFAULT_EX),
    routines: clone(DEFAULT_ROUTINES),
    logs: [],
    body: [],
    weights: {},
  };
}
function legacyPlan(raw: Record<string, unknown>): Plan {
  const plan = emptyData(),
    weights = record(raw.weights);
  for (const [id, v] of Object.entries(weights)) {
    const ex = plan.exercises.find((x) => x.id === id);
    if (!ex) throw Error("旧版备份动作无效");
    ex.weight = number(v, 0, 1000);
  }
  return plan;
}
export function readData(): StrengthData {
  const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (!raw) return emptyData();
  const x = record(raw),
    plan = x.exercises ? validatePlan(x) : legacyPlan(x);
  return {
    ...plan,
    logs: validateLogs(x.logs, plan.exercises),
    body: validateBody(x.body),
    weights: {},
  };
}
/** Build and validate a complete candidate. The store persists it before publishing it. */
export function importData(
  raw: unknown,
  type: FileType,
  current: StrengthData,
): StrengthData {
  const x = record(raw);
  if (x.app !== "strengthTracker" || ![1, 2].includes(Number(x.version)))
    throw Error("不是有效的训练文件或版本不支持");
  if (x.version === 2 && x.type !== type)
    throw Error("文件类型不匹配，请使用对应的导入按钮");
  if (x.version === 1 && type !== "backup")
    throw Error("旧版备份请使用“导入完整备份”");
  const candidate = clone(current);
  if (type === "backup") {
    const plan = x.version === 1 ? legacyPlan(x) : validatePlan(x);
    return {
      ...plan,
      logs: validateLogs(x.logs, plan.exercises),
      body: validateBody(x.body),
      weights: {},
    };
  }
  if (type === "plan") {
    const plan = validatePlan(x);
    for (const old of current.exercises.filter((e) =>
      current.logs.some((l) => l.exId === e.id),
    )) {
      const next = plan.exercises.find((e) => e.id === old.id);
      if (!next) plan.exercises.push(clone(old));
      else if (next.name !== old.name || next.part !== old.part) {
        const archived = { ...old, id: uid() };
        plan.exercises.push(archived);
        candidate.logs.forEach((l) => {
          if (l.exId === old.id) l.exId = archived.id;
        });
      }
    }
    return { ...candidate, ...plan };
  }
  const exercises = validateExercises(x.exercises),
    logs = validateLogs(x.logs, exercises),
    remap = new Map<string, string>();
  for (const e of exercises.filter((e) => logs.some((l) => l.exId === e.id))) {
    const old = candidate.exercises.find((v) => v.id === e.id);
    if (!old) candidate.exercises.push(e);
    else if (old.name !== e.name || old.part !== e.part) {
      const match = candidate.exercises.find(
        (v) => v.name === e.name && v.part === e.part && v.note === e.note,
      );
      const id = match?.id || uid();
      remap.set(e.id, id);
      if (!match) candidate.exercises.push({ ...e, id });
    }
  }
  for (const log of logs) {
    log.exId = remap.get(log.exId) || log.exId;
    const old = candidate.logs.find((l) => l.id === log.id);
    if (
      old &&
      JSON.stringify(validateLogs([old], candidate.exercises)[0]) !==
        JSON.stringify(log)
    )
      throw Error("同编号记录内容冲突，请核对文件或使用完整备份恢复");
    if (!old) candidate.logs.push(log);
  }
  return candidate;
}
export function exportData(data: StrengthData, type: FileType) {
  const payload =
    type === "plan"
      ? { exercises: data.exercises, routines: data.routines }
      : type === "records"
        ? { exercises: data.exercises, logs: data.logs }
        : data;
  const url = URL.createObjectURL(
    new Blob(
      [
        JSON.stringify(
          {
            app: "strengthTracker",
            version: 2,
            type,
            exportedAt: new Date().toISOString(),
            ...payload,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    ),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `力量训练_${type}_${today()}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

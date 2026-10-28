import { describe, expect, it, vi, afterEach } from "vitest";
import { emptyData, importData, readData, STORAGE_KEY } from "./model";
import { useStrength } from "./useStrength";
afterEach(() => vi.unstubAllGlobals());
function storage(initial: unknown) {
  let value = JSON.stringify(initial);
  const setItem = vi.fn((_key: string, next: string) => {
    value = next;
  });
  vi.stubGlobal("localStorage", { getItem: () => value, setItem });
  return { setItem, read: () => JSON.parse(value) };
}
describe("legacy storage and import identity", () => {
  it("migrates old weights without changing the storage key", () => {
    storage({ logs: [], body: [], weights: { squat: 4.5 } });
    expect(STORAGE_KEY).toBe("strengthTracker_v1");
    expect(readData().exercises.find((e) => e.id === "squat")?.weight).toBe(
      4.5,
    );
  });
  it("archives a replaced exercise referenced by historical records", () => {
    const data = emptyData();
    data.logs.push({
      id: "log1",
      date: "2026-10-01",
      exId: "squat",
      sets: 3,
      reps: 12,
      weight: 0,
      unit: "次",
      pain: 0,
      note: "",
    });
    const plan = emptyData();
    plan.exercises[0].name = "新动作";
    const candidate = importData(
      { app: "strengthTracker", version: 2, type: "plan", ...plan },
      "plan",
      data,
    );
    expect(candidate.logs[0].exId).not.toBe("squat");
    expect(
      candidate.exercises.find((e) => e.id === candidate.logs[0].exId)?.name,
    ).toBe("徒手深蹲");
    expect(data.logs[0].exId).toBe("squat");
  });
  it("rejects conflicting log IDs and invalid calendar dates", () => {
    const data = emptyData();
    data.logs.push({
      id: "log1",
      date: "2026-10-01",
      exId: "squat",
      sets: 3,
      reps: 12,
      weight: 0,
      unit: "次",
      pain: 0,
      note: "",
    });
    const raw = {
      app: "strengthTracker",
      version: 2,
      type: "records",
      exercises: data.exercises,
      logs: [{ ...data.logs[0], weight: 10 }],
    };
    expect(() => importData(raw, "records", data)).toThrow("冲突");
    raw.logs[0] = { ...raw.logs[0], date: "2026-02-30" };
    expect(() => importData(raw, "records", data)).toThrow();
    expect(data.logs[0].weight).toBe(0);
  });
  it("does not publish a mutation when persistence fails", () => {
    const stored = storage(emptyData()),
      store = useStrength();
    stored.setItem.mockImplementation(() => {
      throw Error("quota");
    });
    expect(
      store.update((d) => {
        d.exercises[0].weight = 20;
      }),
    ).toBe(false);
    expect(store.data.value.exercises[0].weight).toBe(0);
    expect(stored.read().exercises[0].weight).toBe(0);
  });
  it("does not overwrite unreadable existing storage with defaults", () => {
    const stored = storage({ invalid: true }),
      store = useStrength();
    expect(
      store.update((d) => {
        d.logs = [];
      }),
    ).toBe(false);
    expect(stored.setItem).not.toHaveBeenCalled();
    expect(store.commit(emptyData(), true)).toBe(true);
  });
});

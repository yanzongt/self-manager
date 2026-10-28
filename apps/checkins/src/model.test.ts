import { describe, expect, it } from "vitest";
import { daily, localDay, type Item } from "./model";
describe("daily statistics", () => {
  it("splits sessions at local midnight and includes a running timer", () => {
    const midnight = new Date(2026, 9, 26).getTime();
    const items: Item[] = [
      {
        id: "a",
        name: "count",
        type: "count",
        records: [{ start: midnight }, { start: midnight + 1000 }],
      },
      {
        id: "b",
        name: "timer",
        type: "timer",
        records: [{ start: midnight - 60000, end: midnight + 120000 }],
        activeSince: midnight + 180000,
      },
    ];
    const result = daily(items, midnight + 240000);
    expect(result.counts[localDay(midnight)]).toBe(2);
    expect(result.times[localDay(midnight - 1)]).toBe(60000);
    expect(result.times[localDay(midnight)]).toBe(180000);
  });
});

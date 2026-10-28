import { describe, it, expect } from "vitest";
import {
  checkCapabilities,
  normalizeConfig,
  requestConfig,
  validatePool,
} from "./model";
describe("investment request compatibility", () => {
  it("restores CLI pools and legacy symmetric thresholds", () => {
    const config = normalizeConfig({
      pool: { A: "资产甲", B: "资产乙" },
      weights: { A: 0.6, B: 0.2 },
      threshold: 0.03,
      strategy: "ma_band",
    });
    expect(config.pool.map((s) => s.weight)).toEqual([0.6, 0.2]);
    expect(config.buy_threshold).toBe(0.03);
    expect(config.sell_threshold).toBe(0.03);
    expect(config.strategies).toEqual(["ma_band"]);
  });
  it("normalizes inactive funding fields without mutating the draft", () => {
    const draft = normalizeConfig({
      ma_trade_mode: "independent",
      ma_buy_budget_mode: "cash_plus_extra",
      ma_funding_mode: "auto_contribute",
      pool: [{ ticker: " a ", name: " 资产甲 ", weight: 1 }],
    });
    const request = requestConfig(draft);
    expect(request.ma_funding_mode).toBe("cash");
    expect(request.pool[0].ticker).toBe("A");
    expect(draft.ma_funding_mode).toBe("auto_contribute");
  });
  it("rejects outdated engines before submitting new options", () => {
    const config = normalizeConfig({ ma_trade_mode: "independent" });
    expect(() => checkCapabilities(config, {})).toThrow("后台版本过旧");
    expect(() =>
      checkCapabilities(config, { ma_independent_version: 1 }),
    ).not.toThrow();
  });
  it("rejects over-allocation and duplicate canonical tickers", () => {
    expect(() =>
      validatePool(
        requestConfig(
          normalizeConfig({
            pool: [
              { ticker: "a", name: "", weight: 0.8 },
              { ticker: " A ", name: "", weight: 0.1 },
            ],
          }),
        ).pool,
      ),
    ).toThrow("重复");
    expect(() =>
      validatePool([{ ticker: "A", name: "", weight: 1.1 }]),
    ).toThrow("100%");
  });
});

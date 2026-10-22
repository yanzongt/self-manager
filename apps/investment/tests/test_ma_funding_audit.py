"""独立审计自动补款：不用引擎账本/绩效函数作参考，按标量账本及基金份额净值核对。"""

from dataclasses import replace
import unittest

import numpy as np
import pandas as pd

from f_analysis import BacktestConfig, BacktestEngine, DollarCostAveraging, MABand, StockPool
from f_analysis.analytics import period_performance
from f_analysis.research import evaluate_robustness, subperiod_analysis


def reference_ledger(prices, *, initial, fee, window, buy, sell, amount, fraction, weights, start=0, buy_first_only=False, sell_first_only=False, budget_mode="fixed", extra_amount=0):
    """独立标量模拟。新增本金按入金前单位净值申购份额，成交手续费由入金后的净值承担。"""
    cash, capital, units = float(initial), float(initial), float(initial)
    quantity = dict.fromkeys(prices.columns, 0.0)
    basis = dict.fromkeys(prices.columns, 0.0)
    marks, buys, sells = {}, {}, {}
    fees = realized = 0.0
    peak, previous_nav = 1.0, 1.0
    rows, fills, flow_rows = [], [], [(prices.index[start], initial)]

    def signals(i):
        for ticker in prices:
            if pd.isna(prices.iloc[i][ticker]):
                continue
            quotes = [float(value) for value in prices[ticker].iloc[:i + 1] if pd.notna(value)]
            if len(quotes) < window:
                continue
            average = sum(quotes[-window:]) / window
            buy_now = quotes[-1] < average * (1 - buy)
            sell_now = quotes[-1] > average * (1 + sell)
            if len(quotes) > window:
                previous_average = sum(quotes[-window-1:-1]) / window
                if buy_first_only and quotes[-2] < previous_average * (1 - buy):
                    buy_now = False
                if sell_first_only and quotes[-2] > previous_average * (1 + sell):
                    sell_now = False
            if buy_now and weights[ticker] > 0:
                buys[ticker] = (weights[ticker] if budget_mode == "cash_plus_extra" else amount * weights[ticker], prices.index[i])
            if sell_now and quantity[ticker] > 0:
                sells[ticker] = (fraction, prices.index[i])

    if start:
        signals(start - 1)
    for i in range(start, len(prices)):
        date, quoted = prices.index[i], prices.iloc[i]
        marks.update({t: float(p) for t, p in quoted.items() if pd.notna(p)})
        for ticker in list(sells):
            if pd.isna(quoted[ticker]):
                continue
            share, signal_date = sells.pop(ticker)
            sold = quantity[ticker] * share
            notional = sold * marks[ticker]
            cost = notional * fee
            realized += notional - cost - basis[ticker] * share
            cash += notional - cost
            quantity[ticker] *= 1 - share
            basis[ticker] *= 1 - share
            fees += cost
            fills.append((date, ticker, "sell", sold, notional, cost, signal_date))

        ready = [t for t in buys if pd.notna(quoted[t])]
        required = sum(buys[t][0] for t in ready)
        budgets = {}
        if budget_mode == "cash_plus_extra" and ready:
            budgets = {t: (cash + extra_amount) * buys[t][0] / required for t in ready}
            added = extra_amount
        else:
            added = max(0.0, required - cash)
        if added < max(1.0, required) * 1e-10:
            added = 0.0
        if added:
            value_before_deposit = cash + sum(q * marks[t] for t, q in quantity.items() if q)
            units += added / (value_before_deposit / units)
            capital += added
            cash += added
            flow_rows.append((date, added))
        for ticker in ready:
            budget, signal_date = buys.pop(ticker)
            budget = budgets.get(ticker, budget)
            notional = budget / (1 + fee)
            cost = budget - notional
            purchased = notional / marks[ticker]
            cash -= budget
            quantity[ticker] += purchased
            basis[ticker] += budget
            fees += cost
            if purchased > 0:
                fills.append((date, ticker, "buy", purchased, notional, cost, signal_date))
        cash = 0.0 if budget_mode == "cash_plus_extra" and ready else max(0.0, cash)
        market_value = sum(q * marks[t] for t, q in quantity.items() if q)
        equity = cash + market_value
        nav = equity / units
        peak = max(peak, nav)
        rows.append(dict(date=date, cash=cash, market_value=market_value, equity=equity,
                         total_contributed=capital, contribution=added, fees=fees,
                         realized_pnl=realized, unrealized_pnl=market_value - sum(basis.values()),
                         cumulative_pnl=equity-capital, total_return=nav-1,
                         daily_return=nav/previous_nav-1, drawdown=nav/peak-1))
        previous_nav = nav
        signals(i)
    return pd.DataFrame(rows).set_index("date"), fills, flow_rows


def audit_case(seed):
    rng = np.random.default_rng(seed)
    days = np.arange(96)
    prices = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0, 0.08, len(days))) +
                         0.15 * np.sin(days / (3 + n))) for n, t in enumerate(("A", "B", "C"))},
                         index=pd.bdate_range("2023-11-01", periods=len(days)))
    for ticker in ("B", "C"):
        prices.loc[rng.random(len(days)) < 0.13, ticker] = np.nan
    initial = (0.01, 50, 5000)[seed % 3]
    fee = (0, 0.0003, 0.01)[(seed // 2) % 3]
    weights = {"A": 0.5, "B": 0.3, "C": 0.0 if seed % 2 else 0.2}
    options = dict(initial=initial, fee=fee, window=2 + seed % 6, buy=0.02 + seed % 4 * 0.01,
                   sell=0.015 + seed % 3 * 0.015, amount=(10, 1000, 20000)[(seed // 3) % 3],
                   fraction=(0.25, 0.5, 1.0)[seed % 3], weights=weights)
    strategy = MABand(window=options["window"], buy_threshold=options["buy"], sell_threshold=options["sell"],
                      weights=weights, trade_mode="independent", buy_amount=options["amount"],
                      sell_fraction=options["fraction"], funding_mode="auto_contribute")
    engine = BacktestEngine(StockPool.from_tickers(prices.columns), BacktestConfig(initial, fee))
    return prices, options, strategy, engine


class AutoFundingAuditTests(unittest.TestCase):
    def test_32_randomized_accounts_match_independent_cash_and_trade_ledger(self):
        for seed in range(32):
            with self.subTest(seed=seed):
                prices, options, strategy, engine = audit_case(seed)
                expected, fills, flows = reference_ledger(prices, **options)
                actual = engine.run(prices, strategy)
                columns = ["cash", "equity", "market_value", "contribution", "total_contributed",
                           "fees", "realized_pnl", "unrealized_pnl", "cumulative_pnl"]
                np.testing.assert_allclose(actual.history[columns], expected[columns], rtol=1e-9, atol=1e-7)
                self.assertEqual(list(zip(actual.fills.date, actual.fills.ticker, actual.fills.side)), [row[:3] for row in fills])
                np.testing.assert_allclose(actual.fills[["quantity", "notional", "fee"]],
                                           [row[3:6] for row in fills], rtol=1e-9, atol=1e-7)
                self.assertEqual(actual.contributions.date.tolist(), [row[0] for row in flows])
                np.testing.assert_allclose(actual.contributions.amount, [row[1] for row in flows], atol=1e-7)
                self.assertTrue((actual.fills.signal_date < actual.fills.date).all())
                self.assertTrue((actual.positions.quantity >= 0).all())
                self.assertTrue((actual.history.cash >= 0).all())
                self.assertNotIn("insufficient_cash", actual.orders.status.tolist())
                self.assertNotIn("partial", actual.orders.status.tolist())

    def test_first_entry_and_cash_plus_extra_match_16_reference_accounts(self):
        for seed in range(16):
            with self.subTest(seed=seed):
                prices, options, strategy, engine = audit_case(seed)
                first_buy, first_sell = bool(seed % 2), bool((seed // 2) % 2)
                extra = (0, 100, 5000)[seed % 3]
                expected, fills, flows = reference_ledger(prices, **options, buy_first_only=first_buy,
                    sell_first_only=first_sell, budget_mode="cash_plus_extra", extra_amount=extra)
                actual = engine.run(prices, replace(strategy, buy_first_only=first_buy,
                    sell_first_only=first_sell, buy_budget_mode="cash_plus_extra", extra_amount=extra))
                columns = ["cash", "equity", "contribution", "total_contributed", "fees", "total_return", "drawdown"]
                np.testing.assert_allclose(actual.history[columns], expected[columns], rtol=1e-8, atol=1e-7)
                self.assertEqual(list(zip(actual.fills.date, actual.fills.ticker, actual.fills.side)), [row[:3] for row in fills])
                np.testing.assert_allclose(actual.fills[["quantity", "notional", "fee"]], [row[3:6] for row in fills], rtol=1e-8, atol=1e-7)
                np.testing.assert_allclose(actual.contributions.amount, [row[1] for row in flows], atol=1e-7)
                self.assertTrue((actual.history.cash >= 0).all())

    def test_returns_match_independent_unit_price_for_12_randomized_cases(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                prices, options, strategy, engine = audit_case(seed)
                expected, _, _ = reference_ledger(prices, **options)
                actual = engine.run(prices, strategy)
                columns = ["daily_return", "total_return", "drawdown"]
                np.testing.assert_allclose(actual.history[columns], expected[columns], rtol=1e-9, atol=1e-9)
                monthly = period_performance(actual.history, options["initial"], "ME")
                month_ends = (1 + expected.total_return).resample("ME").last()
                np.testing.assert_allclose(monthly["return"], month_ends / month_ends.shift(1, fill_value=1) - 1)
                self.assertAlmostEqual(monthly.pnl.sum(), actual.summary["total_pnl"], places=6)

    def test_tiny_initial_capital_large_top_up_does_not_create_negative_nav(self):
        prices = pd.DataFrame({"A": [100, 80, 80]}, index=pd.bdate_range("2024-01-01", periods=3))
        strategy = MABand(window=2, trade_mode="independent", buy_amount=10000,
                          funding_mode="auto_contribute")
        actual = BacktestEngine(StockPool.from_tickers(["A"]), BacktestConfig(1, 0.01)).run(prices, strategy)
        self.assertAlmostEqual(actual.summary["total_contributed"], 10000)
        self.assertAlmostEqual(actual.summary["total_pnl"], -10000 / 101)
        self.assertAlmostEqual(actual.summary["total_return"], -1 / 101)
        self.assertAlmostEqual(actual.summary["max_drawdown"], -1 / 101)
        self.assertTrue((1 + actual.history.total_return > 0).all())

    def test_dca_large_deposit_fees_match_independent_unit_count(self):
        prices = pd.DataFrame({"A": [100, 100]}, index=pd.to_datetime(["2024-01-02", "2024-02-01"]))
        initial, deposit, fee = 1000, 100_000_000, 0.01
        first_value = initial / (1 + fee)
        units_after_deposit = initial + deposit / (first_value / initial)
        final_value = first_value + deposit / (1 + fee)
        expected_return = final_value / units_after_deposit - 1
        actual = BacktestEngine(StockPool.from_tickers(["A"]), BacktestConfig(initial, fee)).run(
            prices, DollarCostAveraging(deposit, "monthly"))
        self.assertAlmostEqual(actual.summary["total_return"], expected_return)
        self.assertAlmostEqual(actual.summary["max_drawdown"], expected_return)
        self.assertGreater(actual.history.daily_return.min(), -1)
        monthly = period_performance(actual.history, initial, "ME")
        self.assertAlmostEqual(float((1 + monthly["return"]).prod() - 1), expected_return)
        self.assertAlmostEqual(actual.summary["total_pnl"], final_value - initial - deposit)

    def test_perturbation_results_match_fresh_reference_ledgers(self):
        prices, options, strategy, engine = audit_case(4)
        actual = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy),
                                     {"subperiod_count": 3, "sensitivity_enabled": True,
                                      "perturbation": 0.1, "weights": options["weights"]})
        for row in actual.sensitivity.to_dict("records"):
            varied = dict(options)
            if row["parameter"] != "baseline":
                varied["buy" if row["parameter"] == "buy_threshold" else "sell"] = row["value"]
            expected, _, _ = reference_ledger(prices, **varied)
            self.assertAlmostEqual(row["total_return"], expected.iloc[-1].total_return, places=8)
            self.assertAlmostEqual(row["total_contributed"], expected.iloc[-1].total_contributed, places=7)
            self.assertAlmostEqual(row["total_pnl"], expected.iloc[-1].cumulative_pnl, places=7)
            subreturns = []
            for indices in np.array_split(np.arange(len(prices)), 3):
                segment, _, _ = reference_ledger(prices.iloc[:indices[-1] + 1], **varied, start=int(indices[0]))
                subreturns.append(segment.iloc[-1].total_return)
            self.assertAlmostEqual(row["subperiod_return_std"], float(np.std(subreturns)), places=8)

    def test_subperiods_match_fresh_reference_accounts_with_prior_signal_history(self):
        prices, options, strategy, engine = audit_case(4)
        frame, _ = subperiod_analysis(engine, prices, strategy, 4, options["weights"])
        for part, indices in zip(frame.to_dict("records"), np.array_split(np.arange(len(prices)), 4)):
            expected, _, _ = reference_ledger(prices.iloc[:indices[-1] + 1], **options, start=int(indices[0]))
            final = expected.iloc[-1]
            for key in ("total_return", "total_contributed", "cumulative_pnl"):
                self.assertAlmostEqual(part["total_pnl" if key == "cumulative_pnl" else key], final[key], places=7)

    def test_appending_future_prices_cannot_change_past_funding_or_trades(self):
        prices, _, strategy, engine = audit_case(4)
        short, long = engine.run(prices.iloc[:60], replace(strategy)), engine.run(prices, replace(strategy))
        pd.testing.assert_frame_equal(short.history, long.history.iloc[:60])
        pd.testing.assert_frame_equal(short.fills, long.fills.loc[long.fills.date <= prices.index[59]].reset_index(drop=True))
        pd.testing.assert_frame_equal(short.contributions, long.contributions.loc[long.contributions.date <= prices.index[59]].reset_index(drop=True))


if __name__ == "__main__":
    unittest.main()

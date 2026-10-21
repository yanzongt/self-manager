"""多资产引擎：资金守恒、目标权重、时钟和非同步行情。"""

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from f_analysis import (
    BacktestConfig,
    BacktestEngine,
    BaseStrategy,
    BuyAndHold,
    FixedWeightRebalance,
    MABand,
    StockPool,
)
from f_analysis.adapters import pair_backtest
from f_analysis.analytics import correlation_analysis
from f_analysis.reporting import compare_results


def frame(a, b, dates=None):
    return pd.DataFrame(
        {"A": a, "B": b},
        index=dates
        if dates is not None
        else pd.bdate_range("2024-01-01", periods=len(a)),
    )


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.pool = StockPool({"A": "资产A", "B": "资产B"})
        self.engine = BacktestEngine(self.pool, BacktestConfig(1000))

    def assert_balanced(self, result, initial=1000):
        h = result.history
        np.testing.assert_allclose(h["equity"], h["cash"] + h["market_value"])
        np.testing.assert_allclose(
            h["equity"] - initial, h["realized_pnl"] + h["unrealized_pnl"], atol=1e-8
        )
        self.assertTrue((h["cash"] >= 0).all())
        self.assertTrue((result.positions["quantity"] >= 0).all())
        self.assertAlmostEqual(result.fills["fee"].sum(), result.summary["total_fees"])
        self.assertAlmostEqual(result.trades["pnl"].sum(), result.summary["total_pnl"])

    def test_buy_hold_does_not_implicitly_rebalance(self):
        result = self.engine.run(frame([100, 200, 300], [100, 100, 100]), BuyAndHold())
        self.assertEqual(result.summary["final_equity"], 2000)
        self.assertEqual(len(result.fills), 2)
        self.assertEqual(
            result.positions.query("ticker == 'A'")["quantity"].tolist(), [5, 5, 5]
        )
        self.assertEqual(result.orders["status"].tolist(), ["filled", "filled"])
        self.assert_balanced(result)

    def test_comparison_rejects_different_cash_or_date_ranges(self):
        prices = frame([100, 110, 120], [100, 100, 100])
        original = self.engine.run(prices, BuyAndHold())
        different_cash = BacktestEngine(self.pool, BacktestConfig(2000)).run(
            prices, BuyAndHold()
        )
        shorter = self.engine.run(prices.iloc[:2], BuyAndHold())
        for other in [different_cash, shorter]:
            with self.assertRaises(ValueError):
                compare_results({"one": original, "two": other})

    def test_each_observation_rebalance_matches_hand_calculated_returns(self):
        prices = frame([100, 200, 100], [100, 100, 200])
        result = self.engine.run(
            prices, FixedWeightRebalance(frequency="each_observation")
        )
        expected = 1000 * 1.5 * 1.25
        self.assertAlmostEqual(result.summary["final_equity"], expected)
        self.assert_balanced(result)
        legacy = pair_backtest(prices, rebalance=True)
        np.testing.assert_allclose(
            legacy.history["equity"], result.history["equity"] / 1000
        )

    def test_fee_cash_and_average_cost_reconcile_on_partial_sales(self):
        engine = BacktestEngine(self.pool, BacktestConfig(1000, 0.01))
        result = engine.run(
            frame([100, 200, 80, 140], [100, 60, 160, 100]),
            FixedWeightRebalance(frequency="each_observation"),
        )
        self.assert_balanced(result)
        self.assertGreater(result.summary["total_fees"], 0)
        self.assertGreater(result.summary["closed_trades"], 0)
        self.assertEqual(result.summary["open_trades"], 2)

    def test_simultaneous_ma_entries_share_funds_and_do_not_rebalance_while_held(self):
        prices = frame([100, 80, 70, 65], [100, 80, 70, 60])
        result = self.engine.run(prices, MABand(window=2))
        buys = result.fills.query("side == 'buy'")
        self.assertEqual(len(buys), 2)
        self.assertEqual(buys["date"].tolist(), [prices.index[2]] * 2)
        np.testing.assert_allclose(buys["notional"], [500, 500])
        self.assertEqual(
            result.positions.query("ticker == 'A'")["quantity"].iloc[-1], 500 / 70
        )
        self.assert_balanced(result)

    def test_missing_quotes_are_valued_but_never_used_for_execution(self):
        prices = frame([100, 80, np.nan, 70, 100, 110], [10] * 6)
        result = self.engine.run(prices, MABand(window=2, weights={"A": 1, "B": 0}))
        self.assertEqual(
            result.fills["date"].tolist(), [prices.index[3], prices.index[5]]
        )
        self.assertEqual(result.fills["price"].tolist(), [70, 110])
        self.assertEqual(len(result.history), 6)
        # 持仓停牌只估值，不产生虚构成交。
        held = self.engine.run(frame([100, np.nan, 120], [100, 110, 120]), BuyAndHold())
        self.assertEqual(held.history["market_value"].iloc[1], 1050)
        self.assertEqual(len(held.fills), 2)
        self.assert_balanced(held)

    def test_later_listing_does_not_truncate_pool_history(self):
        prices = frame([100, 110, 120, 130], [np.nan, np.nan, 20, 22])
        result = self.engine.run(prices, BuyAndHold())
        self.assertEqual(result.history.index[0], prices.index[0])
        self.assertEqual(
            result.fills["date"].tolist(), [prices.index[0], prices.index[2]]
        )
        self.assertEqual(result.fills["price"].tolist(), [100, 20])
        self.assertEqual(result.summary["final_equity"], 1200)
        self.assert_balanced(result)

    def test_partial_targets_do_not_touch_other_holdings_and_sells_fund_buys(self):
        class Switch(BaseStrategy):
            def initial_targets(self, pool):
                return {"A": 1}

            def on_close(self, context):
                return {"A": 0, "B": 1} if len(context.history) == 1 else None

        result = self.engine.run(frame([100, 100, 100], [100, 100, 100]), Switch())
        self.assertEqual(result.fills["side"].tolist(), ["buy", "sell", "buy"])
        self.assertEqual(result.fills["ticker"].tolist(), ["A", "A", "B"])
        self.assert_balanced(result)

        class Partial(Switch):
            def initial_targets(self, pool):
                return {"A": 0.5, "B": 0.5}

            def on_close(self, context):
                return {"A": 0} if len(context.history) == 1 else None

        partial = self.engine.run(frame([100, 100, 100], [100, 150, 200]), Partial())
        self.assertEqual(
            partial.positions.query("ticker == 'B'")["quantity"].tolist(), [5, 5, 5]
        )
        self.assert_balanced(partial)

    def test_no_cash_buys_are_scaled_equally_and_not_automatically_retried(self):
        class Oversubscribed(BaseStrategy):
            def initial_targets(self, pool):
                return {"A": 0.8}

            def on_close(self, context):
                return {"B": 1} if len(context.history) == 1 else None

        result = self.engine.run(frame([100] * 3, [100] * 3), Oversubscribed())
        self.assertEqual(result.fills["notional"].tolist(), [800, 200])
        self.assertEqual(result.orders["status"].tolist(), ["filled", "partial"])
        self.assert_balanced(result)

    def test_calendar_schedule_uses_first_observation_of_new_period(self):
        dates = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
        result = self.engine.run(
            frame([100, 110, 120, 130], [100] * 4, dates), FixedWeightRebalance()
        )
        self.assertEqual(set(result.fills["date"]), {dates[0], dates[2]})
        self.assert_balanced(result)

    def test_future_data_cannot_change_past_account_history(self):
        short = frame([100, 80, 70, 100], [100, 100, 100, 100])
        long = frame([100, 80, 70, 100, 110, 90], [100] * 6)
        first = self.engine.run(short, MABand(window=2))
        second = self.engine.run(long, MABand(window=2))
        assert_frame_equal(first.history, second.history.loc[first.history.index])
        self.assertEqual(first.orders.iloc[-1]["status"], "pending")
        self.assertEqual(second.orders.iloc[-1]["status"], "pending")

    def test_invalid_targets_and_bad_prices_are_rejected(self):
        prices = frame([100, 110], [100, 100])
        for weights in [{"A": 1, "B": 1}, {"A": -0.1}, {"UNKNOWN": 0.1}, {"A": np.nan}]:
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                self.engine.run(prices, BuyAndHold(weights))
        with self.assertRaises(ValueError):
            self.engine.run(frame([100, 0], [100, 100]), BuyAndHold())
        with self.assertRaises(ValueError):
            StockPool.from_tickers(["A", "a"])

    def test_correlations_reuse_ragged_prices_without_global_dropna(self):
        returns, correlation = correlation_analysis(
            frame([100, 110, 121], [np.nan, 100, 90])
        )
        self.assertEqual(len(returns), 3)
        self.assertTrue(pd.isna(returns["B"].iloc[1]))
        self.assertAlmostEqual(returns["A"].iloc[1], 0.1)
        self.assertEqual(correlation.shape, (2, 2))


if __name__ == "__main__":
    unittest.main()

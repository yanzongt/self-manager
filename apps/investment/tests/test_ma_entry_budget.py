"""首次进入偏离区、单侧触发及全现金加额外投入的边界测试。"""

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from f_analysis import BacktestConfig, BacktestEngine, MABand, StockPool
from f_analysis.research import research_config
from scripts.single_stock_backtest import backtest


class MAEntryBudgetTests(unittest.TestCase):
    def prices(self):
        return pd.DataFrame({"A": [100, 80, 60, 40, 80, 120, 160, 80, 60, 40]},
                            index=pd.bdate_range("2024-01-01", periods=10))

    def run_case(self, prices, **options):
        strategy = MABand(window=2, trade_mode="independent", buy_amount=100, sell_fraction=0.5, **options)
        engine = BacktestEngine(StockPool.from_tickers(prices.columns), BacktestConfig(1000))
        return engine.run(prices, strategy)

    def test_each_side_can_independently_require_a_new_entry(self):
        prices = self.prices()
        for first_buy, first_sell, buys, sells in [(False, False, 5, 3), (True, False, 2, 3),
                                                    (False, True, 5, 1), (True, True, 2, 1)]:
            with self.subTest(first_buy=first_buy, first_sell=first_sell):
                result = self.run_case(prices, buy_first_only=first_buy, sell_first_only=first_sell)
                self.assertEqual(int((result.fills.side == "buy").sum()), buys)
                self.assertEqual(int((result.fills.side == "sell").sum()), sells)
        once = self.run_case(prices, buy_first_only=True, sell_first_only=True)
        self.assertEqual(once.fills.date.tolist(), [prices.index[2], prices.index[5], prices.index[8]])

    def test_missing_quotes_do_not_rearm_a_continuous_condition(self):
        prices = pd.DataFrame({"A": [100, 80, np.nan, 60, 80], "B": [100] * 5},
                              index=pd.bdate_range("2024-01-01", periods=5))
        result = self.run_case(prices, buy_first_only=True, weights={"A": 1, "B": 0})
        self.assertEqual(result.fills.side.tolist(), ["buy"])
        self.assertEqual(result.fills.iloc[0].date, prices.index[3])

    def test_return_to_threshold_rearms_and_subperiod_does_not_reset_market_condition(self):
        prices = pd.DataFrame({"A": [100, 60, 30, 20, 10, 10]}, index=pd.bdate_range("2024-01-01", periods=6))
        result = self.run_case(prices, buy_threshold=0.2, buy_first_only=True)
        self.assertEqual(result.fills.loc[result.fills.side == "buy", "date"].tolist(), [prices.index[2], prices.index[5]])
        prices = self.prices()
        strategy = MABand(window=2, trade_mode="independent", buy_first_only=True,
                          sell_first_only=True, buy_budget_mode="cash_plus_extra", extra_amount=100)
        engine = BacktestEngine(StockPool.from_tickers(["A"]), BacktestConfig(1000))
        # Starting inside an existing buy zone must wait for an actual exit and re-entry.
        segment = engine.run(prices, strategy, start_date=prices.index[3])
        self.assertEqual(segment.fills.date.tolist(), [prices.index[8]])
        warm = engine.run(prices, strategy, start_date=prices.index[2])
        self.assertEqual(warm.fills.iloc[0].date, prices.index[2])

    def test_pure_cash_plus_extra_uses_sale_proceeds_and_adds_once_per_buy_day(self):
        prices = self.prices()
        result = self.run_case(prices, buy_first_only=True, sell_first_only=True,
                               buy_budget_mode="cash_plus_extra", extra_amount=100)
        np.testing.assert_allclose(result.fills.notional, [1100, 1100, 1200])
        self.assertEqual(result.contributions.amount.tolist(), [1000, 100, 100])
        self.assertEqual(result.contributions.kind.tolist(), ["initial", "signal_extra", "signal_extra"])
        self.assertAlmostEqual(result.summary["total_contributed"], 1200)
        self.assertAlmostEqual(result.summary["final_cash"], 0)
        self.assertEqual(result.summary["return_method"], "time_weighted")
        self.assertTrue(result.summary["ma_buy_first_only"])

    def test_multiple_stock_buys_share_one_cash_budget_and_one_extra(self):
        prices = self.prices().iloc[:3].assign(B=[100, 80, 60])
        result = self.run_case(prices, weights={"A": 0.6, "B": 0.2}, buy_budget_mode="cash_plus_extra", extra_amount=200)
        np.testing.assert_allclose(result.fills.notional, [900, 300])
        self.assertEqual(result.contributions.amount.tolist(), [1000, 200])
        self.assertAlmostEqual(result.summary["final_cash"], 0)
        # Only A triggers: deploy the entire budget into A, rather than leaving B's share idle.
        prices.B = [100, 100, 100]
        solo = self.run_case(prices, weights={"A": 0.6, "B": 0.2}, buy_budget_mode="cash_plus_extra", extra_amount=200)
        self.assertEqual(solo.fills.ticker.tolist(), ["A"])
        self.assertAlmostEqual(solo.fills.iloc[0].notional, 1200)

    def test_zero_extra_and_no_signal_never_add_money(self):
        prices = self.prices()
        result = self.run_case(prices, buy_first_only=True, sell_first_only=True,
                               buy_budget_mode="cash_plus_extra", extra_amount=0)
        self.assertEqual(result.summary["total_contributed"], 1000)
        self.assertEqual(len(result.contributions), 1)
        self.assertAlmostEqual(result.fills.iloc[0].notional, 1000)
        constant = self.run_case(prices.assign(A=100), buy_budget_mode="cash_plus_extra", extra_amount=100)
        self.assertEqual(constant.summary["additional_contributions"], 0)
        self.assertTrue(constant.fills.empty)

    def test_strategy_reuse_future_invariance_and_single_stock_signal_diagnostics(self):
        prices = self.prices()
        strategy = MABand(window=2, trade_mode="independent", buy_first_only=True, sell_first_only=True,
                          buy_budget_mode="cash_plus_extra", extra_amount=100)
        engine = BacktestEngine(StockPool.from_tickers(["A"]), BacktestConfig(1000))
        first = engine.run(prices, strategy)
        assert_frame_equal(first.history, engine.run(prices, strategy).history)
        short = engine.run(prices.iloc[:7], replace(strategy))
        assert_frame_equal(short.history, first.history.iloc[:7])
        history, _, summary = backtest(prices.A, initial_cash=1000, window=2,
            trade_mode="independent", buy_first_only=True, sell_first_only=True,
            buy_budget_mode="cash_plus_extra", extra_amount=100)
        self.assertEqual(history.signal.tolist(), [0, 1, 0, 0, -1, 0, 0, 1, 0, 0])
        self.assertEqual(summary["ma_buy_budget_mode"], "cash_plus_extra")

    def test_validation_and_both_cli_entrypoints(self):
        for update in ({"ma_buy_first_only": "yes"}, {"ma_sell_first_only": 1},
                       {"ma_buy_budget_mode": "bad"}, {"ma_extra_amount": -1},
                       {"ma_buy_budget_mode": "cash_plus_extra"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                research_config(update)
        from scripts.portfolio_backtest import main as portfolio
        from scripts.single_stock_backtest import main as single
        for call, target, source in [(portfolio, "scripts.portfolio_backtest.get_prices", ["--tickers", "A"]),
                                     (single, "scripts.single_stock_backtest.get_prices", ["--ticker", "A"])]:
            with tempfile.TemporaryDirectory() as directory:
                args = ["backtest", *source, "--strategy", "ma_band", "--ma-window", "2", "--initial-cash", "1000",
                        "--ma-trade-mode", "independent", "--ma-buy-first-only", "--ma-sell-first-only",
                        "--ma-buy-budget-mode", "cash_plus_extra", "--ma-extra-amount", "100",
                        "--ma-sell-fraction", "0.5", "--output-dir", directory, "--no-show"]
                with patch("sys.argv", args), patch(target, return_value=self.prices()), redirect_stdout(io.StringIO()):
                    call()
                summary = json.loads((Path(directory) / "ma_band/summary.json").read_text())
                self.assertTrue(summary["ma_sell_first_only"])
                self.assertEqual(summary["total_contributed"], 1200)


if __name__ == "__main__":
    unittest.main()

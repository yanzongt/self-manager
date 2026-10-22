"""均线独立加仓/减仓：无交替限制、无透支、无做空，仍按次日信号成交。"""

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from f_analysis import BacktestConfig, BacktestEngine, MABand, StockPool
from f_analysis.research import evaluate_robustness, research_config
from scripts.single_stock_backtest import backtest


class IndependentMATests(unittest.TestCase):
    def prices(self):
        return pd.DataFrame({"A": [100, 80, 60, 40, 80, 120, 160]},
                            index=pd.bdate_range("2024-01-01", periods=7))

    def engine(self, prices, cash=1000, fee=0):
        return BacktestEngine(StockPool.from_tickers(prices.columns), BacktestConfig(cash, fee))

    def strategy(self, **options):
        return MABand(window=2, trade_mode="independent", buy_amount=100, sell_fraction=0.5, **options)

    def test_consecutive_buys_and_fractional_sells_at_next_close(self):
        prices = self.prices()
        result = self.engine(prices).run(prices, self.strategy())
        self.assertEqual(result.fills.side.tolist(), ["buy", "buy", "buy", "sell", "sell"])
        self.assertEqual(result.fills.date.tolist(), prices.index[2:].tolist())
        np.testing.assert_allclose(result.fills.quantity, [100 / 60, 100 / 40, 100 / 80, 65 / 24, 65 / 48])
        self.assertAlmostEqual(result.summary["final_quantities"]["A"], 65 / 48)
        self.assertAlmostEqual(result.summary["total_pnl"], 1375 / 3)
        self.assertAlmostEqual(result.summary["final_cash"], 3725 / 3)
        self.assertTrue((result.fills.signal_date < result.fills.date).all())
        self.assertEqual(result.summary["ma_trade_mode"], "independent")
        self.assertEqual(result.summary["additional_contributions"], 0)

    def test_original_full_position_mode_still_alternates(self):
        prices = self.prices()
        result = self.engine(prices).run(prices, MABand(window=2))
        self.assertEqual(result.fills.side.tolist(), ["buy", "sell"])
        self.assertEqual(result.summary["final_quantities"]["A"], 0)

    def test_cash_limits_fees_and_no_short_sales(self):
        prices = self.prices()
        result = self.engine(prices, cash=150, fee=0.01).run(prices, self.strategy())
        buys = result.fills.loc[result.fills.side == "buy"]
        np.testing.assert_allclose(buys.notional + buys.fee, [100, 50])
        self.assertIn("partial", result.orders.status.tolist())
        self.assertIn("insufficient_cash", result.orders.status.tolist())
        self.assertGreaterEqual(result.history.cash.min(), 0)
        self.assertGreaterEqual(result.positions.quantity.min(), 0)
        self.assertAlmostEqual(result.summary["total_pnl"], result.summary["realized_pnl"] + result.summary["unrealized_pnl"])
        rising = prices.assign(A=[100, 120, 160, 200, 240, 280, 320])
        flat = self.engine(rising).run(rising, self.strategy())
        self.assertTrue(flat.fills.empty)
        self.assertEqual(flat.summary["final_equity"], 1000)

    def test_same_day_sells_fund_other_stock_buys_without_rebalancing(self):
        prices = self.prices().assign(B=[100, 100, 100, 100, 90, 70, 50])
        result = self.engine(prices, cash=150).run(prices, self.strategy(weights={"A": 0.5, "B": 0.5}))
        fills = result.fills.loc[result.fills.date == prices.index[5]]
        self.assertEqual(fills.side.tolist(), ["sell", "buy"])
        self.assertEqual(fills.ticker.tolist(), ["A", "B"])
        self.assertAlmostEqual(fills.iloc[1].notional, 50)
        self.assertGreaterEqual(result.history.cash.min(), 0)

    def test_missing_price_waits_and_future_data_do_not_change_past(self):
        prices = self.prices().assign(B=[100] * 7)
        prices.loc[prices.index[2], "A"] = np.nan
        engine = self.engine(prices)
        short = engine.run(prices.iloc[:5], self.strategy())
        long = engine.run(prices, self.strategy())
        self.assertEqual(long.fills.iloc[0].date, prices.index[3])
        assert_frame_equal(short.history, long.history.iloc[:5])

    def test_subperiods_sensitivity_and_single_stock_adapter_preserve_mode(self):
        prices = self.prices()
        engine, strategy = self.engine(prices), self.strategy()
        result = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy),
                                     research_config({"subperiod_count": 2, "sensitivity_enabled": True}))
        self.assertEqual(len(result.subperiods), 2)
        self.assertEqual(len(result.sensitivity), 5)
        varied = engine.run(prices, self.strategy(buy_threshold=0.045))
        self.assertAlmostEqual(result.sensitivity.iloc[1].total_return, varied.summary["total_return"])
        _, _, summary = backtest(prices.A.iloc[:3], initial_cash=1000, window=2,
                                  trade_mode="independent", buy_amount=100, sell_fraction=0.5)
        self.assertEqual(summary["pending_action"], "buy")
        self.assertEqual(summary["ma_buy_amount"], 100)

    def test_auto_contribution_fills_every_budget_and_tracks_only_the_gap(self):
        prices = self.prices()
        engine = self.engine(prices, cash=150)
        result = engine.run(prices, self.strategy(funding_mode="auto_contribute"))
        buys = result.fills.loc[result.fills.side == "buy"]
        np.testing.assert_allclose(buys.notional + buys.fee, [100, 100, 100])
        self.assertEqual(result.contributions.amount.tolist(), [150, 50, 100])
        self.assertEqual(result.contributions.kind.tolist(), ["initial", "signal_top_up", "signal_top_up"])
        self.assertEqual(result.summary["total_contributed"], 300)
        self.assertEqual(result.summary["additional_contributions"], 150)
        self.assertEqual(result.summary["return_method"], "time_weighted")
        self.assertAlmostEqual(result.summary["total_pnl"], result.summary["final_equity"] - 300)
        self.assertNotIn("insufficient_cash", result.orders.status.tolist())
        self.assertNotIn("partial", result.orders.status.tolist())
        self.assertGreaterEqual(result.history.cash.min(), 0)

    def test_top_up_is_not_profit_and_fee_stays_inside_buy_budget(self):
        prices = pd.DataFrame({"A": [100, 80, 80]}, index=pd.bdate_range("2024-01-01", periods=3))
        for fee in (0, 0.01):
            result = self.engine(prices, cash=50, fee=fee).run(prices, self.strategy(funding_mode="auto_contribute"))
            self.assertEqual(result.summary["total_contributed"], 100)
            self.assertAlmostEqual(result.fills.notional.sum() + result.fills.fee.sum(), 100)
            self.assertAlmostEqual(result.summary["total_pnl"], -result.summary["total_fees"])
            self.assertAlmostEqual(result.summary["total_return"], -result.summary["total_fees"] / 100)
            self.assertAlmostEqual(result.summary["max_drawdown"], result.summary["total_return"])

    def test_top_up_waits_for_executable_quotes_and_reuses_sale_proceeds(self):
        prices = self.prices().assign(B=[100] * 7)
        prices.loc[prices.index[2], "A"] = np.nan
        result = self.engine(prices, cash=10).run(prices, self.strategy(weights={"A": 1, "B": 0}, funding_mode="auto_contribute"))
        self.assertEqual(result.contributions.iloc[1].date, prices.index[3])
        self.assertEqual(result.contributions.iloc[1].amount, 90)
        self.assertEqual(result.history.iloc[2].total_contributed, 10)
        prices = self.prices().assign(B=[100, 100, 100, 100, 90, 70, 50])
        result = self.engine(prices, cash=150).run(prices, self.strategy(weights={"A": 0.5, "B": 0.5}, funding_mode="auto_contribute"))
        self.assertEqual(result.summary["additional_contributions"], 0)
        self.assertEqual(len(result.contributions), 1)
        day = result.fills.loc[result.fills.date == prices.index[5]]
        self.assertEqual(day.side.tolist(), ["sell", "buy"])
        self.assertAlmostEqual(day.iloc[1].notional, 50)

    def test_auto_contribution_subperiods_and_variants_keep_funding_mode(self):
        prices = self.prices()
        engine = self.engine(prices, cash=50)
        strategy = self.strategy(funding_mode="auto_contribute")
        result = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy),
                                     research_config({"subperiod_count": 2, "sensitivity_enabled": True}))
        self.assertEqual(result.summary["ma_funding_mode"], "auto_contribute")
        self.assertTrue((result.subperiods.total_contributed >= 50).all())
        direct = engine.run(prices, self.strategy(funding_mode="auto_contribute", buy_threshold=0.045))
        self.assertAlmostEqual(result.sensitivity.iloc[1].total_return, direct.summary["total_return"])
        _, _, summary = backtest(prices.A, initial_cash=150, window=2, trade_mode="independent",
                                  buy_amount=100, sell_fraction=0.5, funding_mode="auto_contribute")
        self.assertEqual(summary["total_contributed"], 300)
        self.assertEqual(summary["return_method"], "time_weighted")

    def test_both_clis_export_auto_contribution_ledger_and_principal(self):
        from scripts.portfolio_backtest import main as portfolio
        from scripts.single_stock_backtest import main as single
        for call, target, source in [
            (portfolio, "scripts.portfolio_backtest.get_prices", ["--tickers", "A"]),
            (single, "scripts.single_stock_backtest.get_prices", ["--ticker", "A"]),
        ]:
            with tempfile.TemporaryDirectory() as directory:
                args = ["backtest", *source, "--strategy", "ma_band", "--ma-window", "2",
                        "--initial-cash", "150", "--ma-buy-amount", "100", "--ma-trade-mode", "independent",
                        "--ma-funding-mode", "auto_contribute", "--ma-sell-fraction", "0.5",
                        "--output-dir", directory, "--no-show"]
                with patch("sys.argv", args), patch(target, return_value=self.prices()), redirect_stdout(io.StringIO()):
                    call()
                root = Path(directory) / "ma_band"
                summary = json.loads((root / "summary.json").read_text())
                self.assertEqual(summary["ma_funding_mode"], "auto_contribute")
                self.assertEqual(summary["total_contributed"], 300)
                self.assertEqual(summary["return_method"], "time_weighted")
                self.assertEqual(pd.read_csv(root / "contributions.csv").amount.tolist(), [150, 50, 100])

    def test_invalid_settings_and_cli_flags(self):
        for update in ({"ma_funding_mode": "bad"}, {"ma_funding_mode": "auto_contribute"}, {"ma_trade_mode": "bad"}, {"ma_buy_amount": 0}, {"ma_sell_fraction": 0},
                       {"ma_sell_fraction": 1.1}, {"ma_sell_fraction": True}, {"ma_buy_amount": float("inf")}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                research_config(update)
        from scripts.portfolio_backtest import main
        from scripts.single_stock_backtest import main as single
        for target, call, extra, output_name in [
            ("scripts.portfolio_backtest.get_prices", main, ["--tickers", "A", "--strategy", "ma_band"], "ma_band"),
            ("scripts.single_stock_backtest.get_prices", single, ["--ticker", "A", "--strategy", "ma_band"], "ma_band"),
        ]:
            with tempfile.TemporaryDirectory() as directory:
                with patch("sys.argv", ["backtest", *extra, "--ma-window", "2", "--ma-trade-mode", "independent", "--ma-buy-amount", "100", "--ma-sell-fraction", "0.5", "--no-show", "--output-dir", directory]), patch(target, return_value=self.prices()), redirect_stdout(io.StringIO()):
                    call()
                root = Path(directory) / output_name
                if (root / "fills.csv").exists():
                    actions = pd.read_csv(root / "fills.csv").side.tolist()
                else:
                    actions = [action for action in pd.read_csv(root / "daily_history.csv").executed_action if action != "hold"]
                self.assertEqual(actions, ["buy", "buy", "buy", "sell", "sell"])
                self.assertEqual(json.loads((root / "summary.json").read_text())["ma_trade_mode"], "independent")


if __name__ == "__main__":
    unittest.main()

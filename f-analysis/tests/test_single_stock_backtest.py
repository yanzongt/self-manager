"""用可手算的行情验证成交时点、收益、费用和回撤。"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_series_equal

from scripts.single_stock_backtest import (
    backtest,
    ma_band_signals,
    main,
    period_performance,
)


def prices(values):
    return pd.Series(
        values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float
    )


class SingleStockBacktestTests(unittest.TestCase):
    def test_buy_hold_is_a_full_strategy_with_first_day_entry_and_no_exit(self):
        close = prices([100, 80, 120, 90])
        history, trades, result = backtest(
            close,
            strategy="buy_hold",
            initial_cash=1000,
            fee_rate=0.01,
        )
        self.assertEqual(result["strategy"], "buy_hold")
        self.assertEqual(
            history["executed_action"].tolist(), ["buy", "hold", "hold", "hold"]
        )
        self.assertEqual(trades.iloc[0]["entry_date"], close.index[0])
        self.assertTrue(pd.isna(trades.iloc[0]["entry_signal_date"]))
        self.assertTrue(pd.isna(trades.iloc[0]["exit_date"]))
        self.assertEqual(trades.iloc[0]["status"], "open")
        self.assertAlmostEqual(result["final_quantity"], 1000 / 101)
        self.assertAlmostEqual(result["final_equity"], 1000 / 101 * 90)
        self.assertAlmostEqual(result["total_fees"], 1000 / 101)
        self.assertAlmostEqual(result["max_drawdown"], -0.25)
        self.assertEqual(result["realized_pnl"], 0)
        self.assertAlmostEqual(result["unrealized_pnl"], result["total_pnl"])
        self.assertIsNone(result["win_rate"])
        self.assertEqual(result["closed_trades"], 0)
        self.assertEqual(result["open_trades"], 1)
        self.assertEqual(result["pending_action"], "none")
        for rule in ["ME", "YE"]:
            period = period_performance(history, 1000, rule)
            self.assertAlmostEqual(period["pnl"].sum(), result["total_pnl"])

    def test_buy_hold_fee_is_included_in_initial_drawdown(self):
        history, _, summary = backtest(
            prices([100, 100]), strategy="buy_hold", fee_rate=0.01
        )
        self.assertAlmostEqual(history["daily_return"].iloc[0], 1 / 1.01 - 1)
        self.assertAlmostEqual(summary["max_drawdown"], 1 / 1.01 - 1)

    def test_independent_buy_hold_matches_existing_benchmark(self):
        close = prices([100, 80, 70, 100, 110, 90])
        ma, _, _ = backtest(close, window=2, fee_rate=0.01)
        hold, _, _ = backtest(close, strategy="buy_hold", fee_rate=0.01)
        np.testing.assert_allclose(ma["buy_hold_equity"], hold["equity"])
        np.testing.assert_allclose(ma["buy_hold_return"], hold["total_return"])

    def test_cli_can_run_each_strategy_alone_with_independent_reports(self):
        import matplotlib

        matplotlib.use("Agg")
        for strategy in ["buy_hold", "ma_band"]:
            with self.subTest(strategy=strategy), tempfile.TemporaryDirectory() as temp:
                close = prices([100, 80, 70, 100, 110, 90])
                with (
                    patch(
                        "sys.argv",
                        [
                            "backtest",
                            "--strategy",
                            strategy,
                            "--ma-window",
                            "2",
                            "--output-dir",
                            temp,
                            "--no-show",
                        ],
                    ),
                    patch(
                        "scripts.single_stock_backtest.get_prices",
                        return_value=close.to_frame("600036.SS"),
                    ) as get,
                    redirect_stdout(io.StringIO()),
                ):
                    main()
                get.assert_called_once()
                comparison = pd.read_csv(Path(temp) / "comparison.csv")
                self.assertEqual(comparison["strategy"].tolist(), [strategy])
                self.assertTrue((Path(temp) / strategy / "daily_history.csv").exists())
                self.assertFalse(
                    (
                        Path(temp)
                        / ("buy_hold" if strategy == "ma_band" else "ma_band")
                    ).exists()
                )
                summary = json.loads(
                    (Path(temp) / strategy / "summary.json").read_text()
                )
                self.assertEqual(summary["strategy"], strategy)

    def test_signal_uses_strict_bands_and_requires_warmup(self):
        signal = ma_band_signals(prices([100, 60, 100]), window=2, threshold=0.25)
        self.assertTrue(pd.isna(signal["ma"].iloc[0]))
        self.assertEqual(signal["signal"].tolist(), [0, 0, 0])
        signal = ma_band_signals(prices([100, 59, 110]), window=2, threshold=0.25)
        self.assertEqual(signal["signal"].tolist(), [0, 1, -1])

    def test_next_close_execution_and_final_signal_not_executed(self):
        close = prices([100, 80, 70, 100, 110, 90])
        history, trades, result = backtest(close, window=2, initial_cash=1000)
        self.assertEqual(
            history["executed_action"].tolist(),
            ["hold", "hold", "buy", "hold", "sell", "hold"],
        )
        trade = trades.iloc[0]
        self.assertEqual(trade["entry_signal_date"], close.index[1])
        self.assertEqual(trade["entry_date"], close.index[2])
        self.assertEqual(trade["exit_signal_date"], close.index[3])
        self.assertEqual(trade["exit_date"], close.index[4])
        self.assertAlmostEqual(result["final_equity"], 1000 / 70 * 110)
        self.assertAlmostEqual(result["realized_pnl"], result["total_pnl"])
        self.assertEqual(result["max_drawdown"], 0)
        self.assertEqual(result["win_rate"], 1)
        self.assertEqual(result["pending_action"], "buy")
        self.assertEqual(result["closed_trades"], 1)

    def test_loss_and_max_drawdown_are_marked_daily(self):
        history, _, result = backtest(
            prices([100, 80, 75, 50, 80, 70]), window=2, initial_cash=1000
        )
        self.assertAlmostEqual(result["final_equity"], 1000 / 75 * 70)
        self.assertAlmostEqual(result["max_drawdown"], 50 / 75 - 1)
        self.assertAlmostEqual(history["equity"].iloc[3], 1000 * 50 / 75)
        self.assertEqual(result["win_rate"], 0)

    def test_fees_on_both_sides_and_buy_hold_benchmark(self):
        history, trades, result = backtest(
            prices([100, 80, 70, 100, 110]), window=2, initial_cash=1000, fee_rate=0.01
        )
        qty = 1000 / (70 * 1.01)
        expected = qty * 110 * 0.99
        self.assertAlmostEqual(result["final_equity"], expected)
        self.assertAlmostEqual(result["total_fees"], qty * (70 + 110) * 0.01)
        self.assertAlmostEqual(trades.iloc[0]["pnl"], expected - 1000)
        self.assertAlmostEqual(history["drawdown"].iloc[2], 1 / 1.01 - 1)
        self.assertAlmostEqual(result["buy_hold_final_equity"], 1000 / 101 * 110)
        np.testing.assert_allclose(
            history["realized_pnl"] + history["unrealized_pnl"],
            history["cumulative_pnl"],
            atol=1e-10,
        )

    def test_open_position_is_not_forcibly_sold(self):
        history, trades, result = backtest(
            prices([100, 80, 70, 60]), window=2, initial_cash=1000
        )
        self.assertEqual(result["closed_trades"], 0)
        self.assertIsNone(result["win_rate"])
        self.assertEqual(result["open_trades"], 1)
        self.assertEqual(trades.iloc[0]["status"], "open")
        self.assertTrue(pd.isna(trades.iloc[0]["exit_date"]))
        self.assertAlmostEqual(result["unrealized_pnl"], 1000 * (60 / 70 - 1))
        self.assertAlmostEqual(result["total_pnl"], result["unrealized_pnl"])
        self.assertEqual(result["realized_pnl"], 0)

    def test_no_trades_and_period_totals_reconcile(self):
        history, trades, result = backtest(
            prices([100] * 70), window=30, initial_cash=1000
        )
        self.assertTrue(trades.empty)
        self.assertIn("entry_date", trades.columns)
        self.assertEqual(result["final_equity"], 1000)
        self.assertEqual(result["max_drawdown"], 0)
        for rule in ["ME", "YE"]:
            period = period_performance(history, 1000, rule)
            self.assertAlmostEqual(period["pnl"].sum(), result["total_pnl"])
        history, _, result = backtest(
            prices([100, 80, 70, 100, 110] + [110] * 65), window=2, initial_cash=1000
        )
        for rule in ["ME", "YE"]:
            period = period_performance(history, 1000, rule)
            self.assertAlmostEqual(period["pnl"].sum(), result["total_pnl"])
            self.assertAlmostEqual(
                (period["return"] + 1).prod() - 1, result["total_return"]
            )

    def test_future_prices_do_not_change_past_actions(self):
        close = prices([100, 80, 70, 100, 110, 90])
        first, _, _ = backtest(close, window=2)
        longer = pd.concat(
            [
                close,
                pd.Series(
                    [10.0, 200.0],
                    index=pd.bdate_range(
                        close.index[-1] + pd.Timedelta(days=1), periods=2
                    ),
                ),
            ]
        )
        second, _, _ = backtest(longer, window=2)
        for col in ["signal", "executed_action", "equity"]:
            assert_series_equal(first[col], second.loc[first.index, col])

    def test_bad_parameters_and_insufficient_prices(self):
        for kwargs in [
            dict(initial_cash=0),
            dict(initial_cash=float("inf")),
            dict(fee_rate=-0.1),
            dict(fee_rate=1),
            dict(window=0),
            dict(threshold=0),
            dict(threshold=1),
            dict(window=30),
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                backtest(prices([100, 80, 70]), **kwargs)
        with self.assertRaises(ValueError):
            backtest(prices([100, 0, 70]), window=2)


if __name__ == "__main__":
    unittest.main()

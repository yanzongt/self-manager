"""定投入金、只买新资金及现金流中性的绩效口径。"""

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

from f_analysis import BacktestConfig, BacktestEngine, DollarCostAveraging, StockPool
from f_analysis.analytics import period_performance
from f_analysis.research import evaluate_robustness, research_config
from f_analysis.web_service import normalize_request


class DcaTests(unittest.TestCase):
    def run_strategy(self, prices, amount=100, frequency="each_observation", weights=None, fee=0):
        engine = BacktestEngine(StockPool.from_tickers(prices.columns), BacktestConfig(1000, fee))
        return engine.run(prices, DollarCostAveraging(amount, frequency, weights))

    def test_constant_prices_deposits_are_not_profit_or_return(self):
        prices = pd.DataFrame({"A": [100] * 4}, index=pd.bdate_range("2024-01-01", periods=4))
        result = self.run_strategy(prices)
        self.assertEqual(result.summary["total_contributed"], 1300)
        self.assertEqual(result.summary["final_equity"], 1300)
        self.assertEqual(result.summary["total_pnl"], 0)
        self.assertEqual(result.summary["total_return"], 0)
        self.assertEqual(result.summary["cagr"], 0)
        self.assertEqual(result.summary["max_drawdown"], 0)
        self.assertEqual(result.contributions.amount.tolist(), [1000, 100, 100, 100])
        self.assertEqual(result.fills.side.tolist(), ["buy"] * 4)
        self.assertTrue((result.history.equity == result.history.total_contributed).all())

    def test_time_weighted_returns_drawdown_and_monthly_pnl_remove_cash_flows(self):
        prices = pd.DataFrame({"A": [100, 200, 100]}, index=pd.to_datetime(["2024-01-02", "2024-02-01", "2024-03-01"]))
        result = self.run_strategy(prices, frequency="monthly")
        np.testing.assert_allclose(result.history.daily_return, [0, 1, -0.5])
        self.assertAlmostEqual(result.summary["total_return"], 0)
        self.assertAlmostEqual(result.summary["total_pnl"], -50)
        self.assertAlmostEqual(result.summary["profit_on_contributed"], -50 / 1200)
        self.assertAlmostEqual(result.summary["max_drawdown"], -0.5)
        monthly = period_performance(result.history, 1000, "ME")
        np.testing.assert_allclose(monthly["return"], [0, 1, -0.5])
        np.testing.assert_allclose(monthly.pnl, [0, 1000, -1050])
        self.assertAlmostEqual(monthly.pnl.sum(), -50)

    def test_weights_apply_to_new_money_without_selling_drifted_holdings(self):
        prices = pd.DataFrame({"A": [100, 200], "B": [100, 100]}, index=pd.bdate_range("2024-01-01", periods=2))
        result = self.run_strategy(prices, amount=200, weights={"A": 0.5, "B": 0.3})
        self.assertEqual(result.fills.side.tolist(), ["buy"] * 4)
        self.assertAlmostEqual(result.summary["final_quantities"]["A"], 5.5)
        self.assertAlmostEqual(result.summary["final_quantities"]["B"], 3.6)
        self.assertAlmostEqual(result.summary["final_cash"], 240)
        self.assertAlmostEqual(result.summary["final_equity"], 1700)
        self.assertAlmostEqual(result.summary["total_pnl"], 500)

    def test_calendar_boundaries_skip_holidays_and_do_not_double_deposit_first_day(self):
        dates = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-02", "2024-02-05", "2024-04-01"])
        prices = pd.DataFrame({"A": [100] * len(dates)}, index=dates)
        monthly = self.run_strategy(prices, frequency="monthly")
        self.assertEqual(monthly.contributions.date.tolist(), [dates[0], dates[2], dates[4]])
        quarterly = self.run_strategy(prices, frequency="quarterly")
        self.assertEqual(quarterly.contributions.date.tolist(), [dates[0], dates[4]])
        weekly = self.run_strategy(prices, frequency="weekly")
        self.assertEqual(weekly.contributions.date.tolist(), [dates[0], dates[3], dates[4]])
        annual = self.run_strategy(prices, frequency="annual")
        self.assertEqual(len(annual.contributions), 1)

    def test_missing_quotes_keep_budget_until_available_and_fees_fit_inside_budget(self):
        prices = pd.DataFrame({"A": [100, 100, 100], "B": [np.nan, np.nan, 100]}, index=pd.bdate_range("2024-01-01", periods=3))
        result = self.run_strategy(prices, fee=0.01)
        self.assertEqual(set(result.fills.loc[result.fills.ticker == "B", "date"]), {prices.index[-1]})
        self.assertAlmostEqual(result.summary["final_equity"] + result.summary["total_fees"], 1200)
        self.assertAlmostEqual(result.summary["total_pnl"], -result.summary["total_fees"])
        self.assertGreaterEqual(result.history.cash.min(), 0)
        self.assertEqual(result.summary["pending_orders"], 0)

    def test_future_prices_and_strategy_reuse_do_not_change_past_results(self):
        prices = pd.DataFrame({"A": [100, 90, 80, 120]}, index=pd.bdate_range("2024-01-01", periods=4))
        engine = BacktestEngine(StockPool.from_tickers(["A"]), BacktestConfig(1000))
        strategy = DollarCostAveraging(100, "each_observation")
        first = engine.run(prices.iloc[:3], strategy)
        second = engine.run(prices, strategy)
        assert_frame_equal(first.history, second.history.iloc[:3])
        assert_frame_equal(second.history, engine.run(prices, strategy).history)

    def test_subperiods_reset_capital_and_schedule(self):
        prices = pd.DataFrame({"A": [100] * 6}, index=pd.bdate_range("2024-01-01", periods=6))
        engine = BacktestEngine(StockPool.from_tickers(["A"]), BacktestConfig(1000))
        strategy = DollarCostAveraging(100, "each_observation")
        result = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy),
                                     research_config({"subperiod_count": 2, "sensitivity_enabled": True}))
        self.assertEqual(result.subperiods.total_contributed.tolist(), [1200, 1200])
        self.assertEqual(result.subperiods.total_return.tolist(), [0, 0])
        self.assertFalse(result.robustness["sensitivity"]["applicable"])

    def test_cli_exports_contributions_and_invalid_settings_rejected(self):
        from scripts.portfolio_backtest import main
        prices = pd.DataFrame({"A": [100] * 4}, index=pd.bdate_range("2024-01-01", periods=4))
        with tempfile.TemporaryDirectory() as directory:
            with patch("sys.argv", ["backtest", "--tickers", "A", "--strategy", "dca", "--dca-amount", "100", "--dca-frequency", "each_observation", "--output-dir", directory, "--no-show"]), patch("scripts.portfolio_backtest.get_prices", return_value=prices), redirect_stdout(io.StringIO()):
                main()
            root = Path(directory)
            self.assertEqual(len(pd.read_csv(root / "dca/contributions.csv")), 4)
            summary = json.loads((root / "dca/summary.json").read_text())
            self.assertEqual(summary["total_contributed"], 100300)
        for update in ({"dca_amount": 0}, {"dca_amount": -1}, {"dca_amount": float("nan")}, {"dca_frequency": "bad"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                normalize_request({"pool": [{"ticker": "A", "weight": 1}], "strategies": ["dca"], **update})


if __name__ == "__main__":
    unittest.main()

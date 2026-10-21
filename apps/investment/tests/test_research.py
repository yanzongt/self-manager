"""动量排名、无前视成交、独立子区间及单因素扰动的可手算验证。"""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from f_analysis import BacktestConfig, BacktestEngine, BuyAndHold, CrossSectionalMomentum, MABand, StockPool
from f_analysis.research import evaluate_robustness, research_config, subperiod_analysis
from f_analysis.reporting import save_result
from f_analysis.web_service import normalize_request


class ResearchTests(unittest.TestCase):
    def engine(self, tickers=("A", "B"), fee=0):
        return BacktestEngine(StockPool.from_tickers(tickers), BacktestConfig(1000, fee))

    def prices(self):
        return pd.DataFrame({"A": [100, 110, 121, 100, 90, 80],
                             "B": [100, 100, 100, 110, 121, 133]},
                            index=pd.bdate_range("2024-01-01", periods=6))

    def test_momentum_ranking_rotation_and_next_close_execution(self):
        prices = self.prices()
        result = self.engine().run(prices, CrossSectionalMomentum(2, 2, 1))
        self.assertEqual(result.fills.ticker.tolist(), ["A", "A", "B"])
        self.assertEqual(result.fills.side.tolist(), ["buy", "sell", "buy"])
        self.assertEqual(result.fills.date.tolist(), [prices.index[3], prices.index[5], prices.index[5]])
        self.assertEqual(result.orders.signal_date.tolist(), [prices.index[2]] * 2 + [prices.index[4]] * 2)
        self.assertAlmostEqual(result.summary["final_equity"], 800)
        self.assertTrue((result.history.iloc[:3].equity == 1000).all())
        charged = self.engine(fee=0.01).run(prices, CrossSectionalMomentum(2, 2, 1))
        self.assertGreater(charged.summary["total_fees"], 0)
        self.assertLess(charged.summary["final_equity"], 800)

    def test_momentum_reuse_ties_and_future_invariance(self):
        prices = self.prices()
        strategy = CrossSectionalMomentum(2, 2, 1)
        engine = self.engine()
        first = engine.run(prices, strategy)
        assert_frame_equal(first.fills, engine.run(prices, strategy).fills)
        changed = prices.copy()
        changed.loc[prices.index[-1], "B"] = 9999
        second = engine.run(changed, strategy)
        assert_frame_equal(first.orders[["ticker", "target_weight", "signal_date"]],
                           second.orders[["ticker", "target_weight", "signal_date"]])
        tied = prices.assign(B=prices.A)[["B", "A"]]
        result = self.engine(("B", "A")).run(tied, CrossSectionalMomentum(2, 2, 1))
        self.assertEqual(result.fills.iloc[0].ticker, "A")

    def test_missing_history_reserves_cash_and_later_listing_can_qualify(self):
        prices = self.prices()
        prices.loc[prices.index[:2], "B"] = np.nan
        result = self.engine().run(prices, CrossSectionalMomentum(2, 2, 2))
        self.assertEqual(result.fills.iloc[0].ticker, "A")
        self.assertAlmostEqual(result.history.iloc[3].cash, 500)
        self.assertIn("B", result.fills.ticker.tolist())
        with self.assertRaises(ValueError):
            self.engine().run(prices, CrossSectionalMomentum(top_n=3))
        for args in [(0, 1, 1), (1, 0, 1), (1, 1, 0), (True, 1, 1), (1.2, 1, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                CrossSectionalMomentum(*args)

    def test_asymmetric_ma_changes_exit_without_changing_entry(self):
        prices = pd.DataFrame({"A": [100, 80, 80, 100, 100]}, index=pd.bdate_range("2024-01-01", periods=5))
        engine = self.engine(("A",))
        narrow = engine.run(prices, MABand(2, buy_threshold=0.05, sell_threshold=0.05))
        wide = engine.run(prices, MABand(2, buy_threshold=0.05, sell_threshold=0.3))
        self.assertEqual(narrow.fills.side.tolist(), ["buy", "sell"])
        self.assertEqual(wide.fills.side.tolist(), ["buy"])
        self.assertEqual(narrow.fills.iloc[0].date, wide.fills.iloc[0].date)
        no_buy = engine.run(prices, MABand(2, buy_threshold=0.3, sell_threshold=0.05))
        self.assertTrue(no_buy.fills.empty)

    def test_subperiod_independent_capital_and_population_dispersion(self):
        prices = pd.DataFrame({"A": [100, 200, 100, 50]}, index=pd.date_range("2020-01-01", periods=4, freq="YS"))
        frame, stats = subperiod_analysis(self.engine(("A",)), prices, BuyAndHold(), 2)
        self.assertEqual(frame.total_return.tolist(), [1, -0.5])
        self.assertAlmostEqual(stats["total_return"]["mean"], 0.25)
        self.assertAlmostEqual(stats["total_return"]["std"], 0.75)
        self.assertAlmostEqual(stats["total_return"]["positive_fraction"], 0.5)
        self.assertAlmostEqual(stats["excess_return"]["std"], 0)
        self.assertEqual(sum(frame.trading_days), len(prices))
        with self.assertRaises(ValueError):
            subperiod_analysis(self.engine(("A",)), prices, BuyAndHold(), 3)

    def test_subperiod_prior_history_warms_signals_without_earlier_trades(self):
        prices = pd.DataFrame({"A": [100, 80, 80, 100]}, index=pd.bdate_range("2024-01-01", periods=4))
        engine = self.engine(("A",))
        result = engine.run(prices, MABand(2), start_date=prices.index[2])
        self.assertEqual(result.fills.iloc[0].date, prices.index[2])
        self.assertAlmostEqual(result.summary["total_return"], 0.25)
        self.assertEqual(result.orders.iloc[0].signal_date, prices.index[1])
        self.assertEqual(result.history.index.tolist(), prices.index[2:].tolist())
        self.assertEqual(engine.run(prices.iloc[2:], MABand(2)).summary["total_return"], 0)

    def test_subperiod_before_a_stock_listing_keeps_the_unavailable_slot_in_cash(self):
        prices = self.prices()
        prices.loc[prices.index[:3], "B"] = np.nan
        frame, _ = subperiod_analysis(self.engine(), prices, BuyAndHold(), 2)
        self.assertAlmostEqual(frame.iloc[0].total_return, 0.105)
        momentum, _ = subperiod_analysis(self.engine(), prices, CrossSectionalMomentum(1, 1, 1), 2)
        self.assertEqual(len(momentum), 2)

    def test_sensitivity_actual_parameter_changes_and_exports(self):
        prices = self.prices()
        engine = self.engine()
        strategy = CrossSectionalMomentum(2, 2, 1)
        config = {**research_config({"subperiod_count": 2, "sensitivity_enabled": True}), "weights": {"A": 0.5, "B": 0.5}}
        result = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy), config)
        self.assertEqual(len(result.sensitivity), 5)
        self.assertEqual(result.sensitivity.value.iloc[1:].tolist(), [1, 3, 1, 3])
        changed = engine.run(prices, CrossSectionalMomentum(1, 2, 1))
        self.assertAlmostEqual(result.sensitivity.iloc[1].total_return, changed.summary["total_return"])
        self.assertEqual(result.sensitivity.iloc[0].return_delta, 0)
        self.assertEqual(strategy.lookback, 2)
        self.assertEqual(result.robustness["sensitivity"]["valid_variants"], 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_result(path, result)
            json.loads((path / "robustness.json").read_text())
            self.assertEqual(len(pd.read_csv(path / "subperiods.csv")), 2)
            self.assertEqual(len(pd.read_csv(path / "sensitivity.csv")), 5)

    def test_ma_perturbations_and_invalid_discrete_boundaries(self):
        engine, prices = self.engine(), self.prices()
        config = research_config({"sensitivity_enabled": True})
        strategy = MABand(2, buy_threshold=0.05, sell_threshold=0.08)
        result = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy), config)
        self.assertEqual(result.sensitivity.parameter.tolist(), ["baseline", "buy_threshold", "buy_threshold", "sell_threshold", "sell_threshold"])
        np.testing.assert_allclose(result.sensitivity.value.iloc[1:], [0.045, 0.055, 0.072, 0.088])
        direct = engine.run(prices, MABand(2, buy_threshold=0.045, sell_threshold=0.08))
        self.assertAlmostEqual(result.sensitivity.iloc[1].total_return, direct.summary["total_return"])
        strategy = CrossSectionalMomentum(1, 1, 1)
        result = evaluate_robustness(engine, prices, strategy, engine.run(prices, strategy), config)
        self.assertEqual(result.robustness["sensitivity"]["invalid_variants"], 2)
        self.assertEqual(result.sensitivity.status.tolist().count("invalid"), 2)

    def test_cli_saves_research_config_and_reports_for_both_entrypoints(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from scripts.portfolio_backtest import main as portfolio
        from scripts.single_stock_backtest import main as single
        for main, target, arguments, names in [
            (portfolio, "scripts.portfolio_backtest.get_prices",
             ["--tickers", "A", "B", "--strategy", "cross_sectional_momentum", "--momentum-lookback", "2", "--momentum-interval", "2"],
             ["cross_sectional_momentum"]),
            (single, "scripts.single_stock_backtest.get_prices",
             ["--ticker", "A", "--ma-window", "2", "--buy-threshold", "0.03", "--sell-threshold", "0.08"],
             ["ma_band", "buy_hold"]),
        ]:
            with tempfile.TemporaryDirectory() as directory:
                with patch("sys.argv", ["backtest", *arguments, "--subperiod-count", "2", "--sensitivity", "--no-show", "--output-dir", directory]), patch(target, return_value=self.prices()), redirect_stdout(io.StringIO()):
                    main()
                path = Path(directory)
                config = json.loads((path / "run_config.json").read_text())["config"]
                self.assertEqual(config["subperiod_count"], 2)
                self.assertTrue(config["sensitivity_enabled"])
                for name in names:
                    self.assertTrue((path / name / "subperiods.csv").is_file())
                    if name != "buy_hold":
                        self.assertEqual(len(pd.read_csv(path / name / "sensitivity.csv")), 5)

    def test_config_validation_and_legacy_threshold_fallback(self):
        self.assertEqual(research_config({"threshold": 0.07})["sell_threshold"], 0.07)
        self.assertEqual(research_config({"threshold": 0.07, "buy_threshold": 0.03})["buy_threshold"], 0.03)
        for update in [{"subperiod_count": 1}, {"subperiod_count": True}, {"subperiod_count": 2.5},
                       {"perturbation": float("nan")}, {"perturbation": 0}, {"momentum_interval": 1.5},
                       {"sell_threshold": 1}, {"buy_threshold": -0.1}, {"sensitivity_enabled": "yes"}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                research_config(update)
        with self.assertRaises(ValueError):
            normalize_request({"pool": [{"ticker": "A", "weight": 1}],
                               "strategies": ["cross_sectional_momentum"], "momentum_top_n": 2})


if __name__ == "__main__":
    unittest.main()

"""股票池文件与多资产 CLI 参数的端到端验证。"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import pandas as pd

from scripts.portfolio_backtest import main


class PortfolioCliTests(unittest.TestCase):
    def test_pool_file_names_and_non_equal_weights_are_saved_and_executed(self):
        prices = pd.DataFrame(
            {"A": [100.0, 110.0, 120.0, 130.0], "B": [100.0, 95.0, 100.0, 110.0]},
            index=pd.bdate_range("2024-01-01", periods=4),
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pool = root / "pool.json"
            pool.write_text(
                json.dumps({"A": "资产甲", "B": "资产乙"}), encoding="utf-8"
            )
            output = root / "results"
            with (
                patch(
                    "sys.argv",
                    [
                        "portfolio",
                        "--pool",
                        str(pool),
                        "--weights",
                        "0.6",
                        "0.2",
                        "--strategy",
                        "buy_hold",
                        "--initial-cash",
                        "1000",
                        "--output-dir",
                        str(output),
                        "--no-show",
                    ],
                ),
                patch(
                    "scripts.portfolio_backtest.get_prices", return_value=prices
                ) as load,
                redirect_stdout(io.StringIO()),
            ):
                main()
            self.assertEqual(load.call_args.args[0], ("A", "B"))
            summary = json.loads((output / "buy_hold/summary.json").read_text())
            self.assertEqual(summary["pool"], {"A": "资产甲", "B": "资产乙"})
            self.assertEqual(summary["weights"], {"A": 0.6, "B": 0.2})
            self.assertAlmostEqual(summary["final_equity"], 6 * 130 + 2 * 110 + 200)
            self.assertAlmostEqual(summary["final_cash"], 200)
            self.assertTrue((output / "analysis/monthly_correlation.csv").exists())
            self.assertFalse((output / "ma_band").exists())

    def test_invalid_allocations_fail_before_loading_data(self):
        for extra in [
            ["--weights", "0.8", "0.8"],
            ["--weights", "0.5"],
            ["--strategy", "all", "buy_hold"],
        ]:
            with (
                self.subTest(extra=extra),
                patch("sys.argv", ["portfolio", "--tickers", "A", "B", *extra]),
                patch("scripts.portfolio_backtest.get_prices") as load,
                patch("sys.stderr", io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main()
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()

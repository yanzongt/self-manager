"""用固定行情验证入口、输出隔离和无窗口运行，不访问 Yahoo Finance。"""

import io
import json
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd

from main import main
from scripts import _runtime, market_data


def fake_download(tickers, **kwargs):
    dates = pd.bdate_range(
        pd.Timestamp.today().normalize() - pd.DateOffset(years=5),
        pd.Timestamp.today().normalize(),
    )
    days = np.arange(len(dates))
    close = pd.DataFrame(
        {
            ticker: 100 * np.exp(0.0002 * days + 0.08 * np.sin(days / (25 + i)))
            for i, ticker in enumerate(tickers)
        },
        index=dates,
    )
    return pd.concat({"Close": close}, axis=1)


class WorkflowTests(unittest.TestCase):
    def test_all_entrypoints_save_separate_outputs_without_showing(self):
        expected = {
            "correlation_analysis": (2, 3),
            "rebalance_comparison": (2, 0),
            "rebalance_analysis": (3, 3),
            "etf_pair_scan": (1, 1),
            "single_stock_backtest": (9, 1),
            "portfolio_backtest": (39, 1),
        }
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(
                market_data, "DEFAULT_CACHE_PATH", Path(temp) / "cache.sqlite3"
            ),
        ):
            for name, (csv_count, png_count) in expected.items():
                with self.subTest(script=name):
                    output = Path(temp) / name
                    with (
                        patch(
                            "sys.argv",
                            ["main.py", name, "--no-show", "--output-dir", str(output)],
                        ),
                        patch("yfinance.download", side_effect=fake_download),
                        patch("matplotlib.pyplot.show") as show,
                        redirect_stdout(io.StringIO()),
                        warnings.catch_warnings(),
                    ):
                        warnings.filterwarnings(
                            "ignore", message="Glyph .* missing from font"
                        )
                        main()
                    show.assert_not_called()
                    self.assertEqual(len(list(output.rglob("*.csv"))), csv_count)
                    self.assertEqual(len(list(output.glob("*.png"))), png_count)
                    self.assertEqual(
                        json.loads((output / "run_config.json").read_text())["script"],
                        name,
                    )
                    if name == "single_stock_backtest":
                        comparison = pd.read_csv(output / "comparison.csv")
                        self.assertEqual(
                            comparison["strategy"].tolist(), ["ma_band", "buy_hold"]
                        )
                        for column in ["start", "end", "initial_cash"]:
                            self.assertEqual(comparison[column].nunique(), 1)
                        self.assertAlmostEqual(
                            comparison.iloc[1]["extra_return_vs_buy_hold"], 0
                        )
                    for csv in output.rglob("*.csv"):
                        if csv.name not in {"trades.csv", "fills.csv", "orders.csv"}:
                            self.assertFalse(pd.read_csv(csv).empty)
                    offline_output = Path(temp) / f"{name}-offline"
                    with (
                        patch(
                            "sys.argv",
                            [
                                "main.py",
                                name,
                                "--no-show",
                                "--offline",
                                "--output-dir",
                                str(offline_output),
                            ],
                        ),
                        patch(
                            "yfinance.download",
                            side_effect=AssertionError("离线运行不应联网"),
                        ) as download,
                        redirect_stdout(io.StringIO()),
                        warnings.catch_warnings(),
                    ):
                        warnings.filterwarnings(
                            "ignore", message="Glyph .* missing from font"
                        )
                        main()
                    download.assert_not_called()
                    for csv in output.rglob("*.csv"):
                        self.assertEqual(
                            csv.read_bytes(),
                            (offline_output / csv.relative_to(output)).read_bytes(),
                        )

    def test_default_directories_are_unique(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(_runtime, "PROJECT_ROOT", Path(temp)),
            patch("sys.argv", ["analysis", "--no-show"]),
            redirect_stdout(io.StringIO()),
        ):
            first, _, _ = _runtime.prepare_run("analysis", "test", {})
            second, _, _ = _runtime.prepare_run("analysis", "test", {})
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, Path(temp) / "outputs" / "analysis")


if __name__ == "__main__":
    unittest.main()

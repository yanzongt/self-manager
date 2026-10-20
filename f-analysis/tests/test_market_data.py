"""验证缓存复用、历史替换、失败回滚及原始行情对齐语义。"""

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

from scripts.market_data import get_prices


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "cache.sqlite3"
        self.output = io.StringIO()
        redirect = redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        self.dates = pd.to_datetime(
            ["2020-01-02", "2023-02-28", "2023-12-29", "2024-02-29", "2024-12-31"]
        )
        self.close = pd.DataFrame(
            {
                "A.SS": [10.0, 12.0, 13.0, 14.0, 15.0],
                "B.SZ": [20.0, 21.0, float("nan"), 22.0, 23.0],
            },
            index=self.dates,
        )
        self.downloader = patch(
            "scripts.market_data.yf.download", side_effect=self.download
        ).start()
        self.addCleanup(patch.stopall)

    def download(self, tickers, **kwargs):
        return pd.concat({"Close": self.close[tickers]}, axis=1)

    def get(self, tickers, **kwargs):
        return get_prices(tickers, cache_path=self.cache, as_of="2024-12-31", **kwargs)

    def test_repeat_and_reordered_combination_reuse_complete_history(self):
        report = Path(self.temp.name) / "run_config.json"
        report.write_text('{"script": "example"}')
        first = self.get(["A.SS", "B.SZ"], report_path=report)
        self.downloader.assert_called_once()
        self.assertEqual(self.downloader.call_args.kwargs["period"], "max")
        self.assertTrue(self.downloader.call_args.kwargs["auto_adjust"])
        self.downloader.reset_mock()
        second = self.get(["B.SZ", "A.SS"], offline=True, report_path=report)
        self.downloader.assert_not_called()
        assert_frame_equal(first, second[["A.SS", "B.SZ"]])
        self.assertTrue(pd.isna(second.loc["2023-12-29", "B.SZ"]))
        metadata = json.loads(report.read_text())
        self.assertEqual(metadata["script"], "example")
        self.assertEqual(metadata["market_data"]["tickers"][0]["source"], "cache")
        self.assertEqual(
            metadata["market_data"]["tickers"][0]["end_date"], "2024-12-31"
        )

    def test_only_new_tickers_downloaded_and_short_period_does_not_limit_cache(self):
        short = self.get(["A.SS"], period="1y")
        self.assertEqual(short.index[0], pd.Timestamp("2024-02-29"))
        self.downloader.reset_mock()
        self.get(["A.SS", "B.SZ"])
        self.assertEqual(self.downloader.call_args.args[0], ["B.SZ"])
        self.downloader.reset_mock()
        long = self.get(["A.SS"], offline=True)
        self.assertEqual(long.index[0], self.dates[0])
        self.downloader.assert_not_called()

    def test_refresh_replaces_earlier_adjusted_prices_and_preserves_other_tickers(self):
        original = self.get(["A.SS", "B.SZ"])
        self.close.loc[self.dates[0], "A.SS"] = 5.0
        self.close = self.close.drop(self.dates[1])
        self.downloader.reset_mock()
        refreshed = self.get(["A.SS"], refresh=True)
        self.assertEqual(self.downloader.call_args.args[0], ["A.SS"])
        self.assertEqual(refreshed.iloc[0, 0], 5.0)
        self.assertNotIn(self.dates[1], refreshed.index)
        result = self.get(["B.SZ"], offline=True)
        assert_frame_equal(original[["B.SZ"]].dropna(), result)

    def test_partial_refresh_failure_does_not_overwrite_any_cached_ticker(self):
        original = self.get(["A.SS", "B.SZ"])
        self.close["A.SS"] *= 2
        self.close["B.SZ"] = float("nan")
        with self.assertRaisesRegex(RuntimeError, "旧缓存保持不变"):
            self.get(["A.SS", "B.SZ"], refresh=True)
        assert_frame_equal(original, self.get(["A.SS", "B.SZ"], offline=True))
        self.downloader.side_effect = TimeoutError("timeout")
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            self.get(["A.SS"], refresh=True)
        assert_frame_equal(original, self.get(["A.SS", "B.SZ"], offline=True))

    def test_offline_missing_and_invalid_modes_never_access_network(self):
        with self.assertRaisesRegex(RuntimeError, "A.SS"):
            self.get(["A.SS"], offline=True)
        self.assertFalse(self.cache.exists())
        with self.assertRaises(ValueError):
            self.get(["A.SS"], refresh=True, offline=True)
        with self.assertRaises(ValueError):
            self.get(["A.SS"], period="bad")
        self.downloader.assert_not_called()
        self.get(["A.SS"])
        self.downloader.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "B.SZ"):
            self.get(["A.SS", "B.SZ"], offline=True)
        self.downloader.assert_not_called()

    def test_database_write_failure_rolls_back_entire_refresh(self):
        original = self.get(["A.SS", "B.SZ"])
        with sqlite3.connect(self.cache) as db:
            db.execute("""CREATE TRIGGER reject_price BEFORE INSERT ON prices
                          WHEN NEW.ticker = 'B.SZ'
                          BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END""")
        self.close *= 2
        with self.assertRaises(sqlite3.IntegrityError):
            self.get(["A.SS", "B.SZ"], refresh=True)
        assert_frame_equal(original, self.get(["A.SS", "B.SZ"], offline=True))

    def test_empty_or_invalid_download_is_not_cached(self):
        for response in [
            pd.DataFrame(),
            pd.DataFrame({"Close": [float("inf")]}, index=self.dates[:1]),
        ]:
            with (
                self.subTest(response=response),
                patch("scripts.market_data.yf.download", return_value=response),
            ):
                with self.assertRaises(RuntimeError):
                    self.get(["A.SS"])
                with self.assertRaisesRegex(RuntimeError, "缺少行情缓存"):
                    self.get(["A.SS"], offline=True)
        with patch(
            "scripts.market_data.yf.download",
            return_value=pd.DataFrame({"Close": [10.0]}, index=self.dates[:1]),
        ):
            self.assertEqual(self.get(["A.SS"]).iloc[0, 0], 10.0)

    def test_calendar_period_and_stale_cache_are_explicit(self):
        self.get(["A.SS"])
        leap = get_prices(
            ["A.SS"],
            period="1y",
            cache_path=self.cache,
            as_of="2024-02-29",
            offline=True,
        )
        self.assertEqual(leap.index[0], pd.Timestamp("2023-02-28"))
        self.assertEqual(leap.index[-1], pd.Timestamp("2024-02-29"))
        self.downloader.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "请刷新"):
            get_prices(
                ["A.SS"],
                period="1y",
                cache_path=self.cache,
                as_of="2030-01-01",
                offline=True,
            )
        self.downloader.assert_not_called()


if __name__ == "__main__":
    unittest.main()

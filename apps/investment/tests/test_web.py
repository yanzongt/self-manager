"""本机网页：真实 HTTP 路由、后台引擎、历史读取和文件导出。"""

from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
from unittest.mock import patch
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pandas as pd

from f_analysis import BacktestConfig, BacktestEngine, BuyAndHold, StockPool
from f_analysis.web_service import WebApplication, normalize_request, write_json
from scripts import market_data
from scripts.web import make_server


def request_data():
    return {
        "pool": [
            {"ticker": "A", "name": "资产甲", "weight": 0.6},
            {"ticker": "B", "name": "资产乙", "weight": 0.2},
        ],
        "strategies": ["buy_hold", "ma_band", "fixed_weight"],
        "initial_cash": 1000,
        "ma_window": 3,
        "threshold": 0.05,
        "period": "5y",
        "data_mode": "offline",
    }


def prices(tickers, **kwargs):
    return pd.DataFrame(
        {
            ticker: [100.0, 80.0, 70.0, 95.0, 110.0, 120.0, 90.0, 100.0]
            for ticker in tickers
        },
        index=pd.bdate_range("2024-01-01", periods=8),
    )


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = WebApplication(
            self.root, price_loader=prices, cache_path=self.root / "cache.sqlite3"
        )
        self.server = make_server(self.app, port=0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.close()
        self.temp.cleanup()

    def http(self, path, payload=None, headers=None):
        combined = {"Content-Type": "application/json", "X-Local-Token": self.app.token}
        combined.update(headers or {})
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.url + path, data=data, headers=combined)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as exc:
            response = exc
        with closing(response):
            return response.status, response.headers, response.read()

    def complete_run(self, payload=None):
        status, _, body = self.http("/api/runs", payload or request_data())
        self.assertEqual(status, 202)
        run_id = json.loads(body)["id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = self.app.job_status(run_id)
            if state["state"] not in ("queued", "running"):
                self.assertEqual(state["state"], "succeeded", state)
                return run_id
            time.sleep(0.02)
        self.fail("后台回测没有在预期时间内完成")

    def test_named_pool_save_load_overwrite_and_restart(self):
        payload = {"name": "我的长期组合", "pool": request_data()["pool"]}
        status, _, body = self.http("/api/pools", payload)
        self.assertEqual(status, 200)
        saved = json.loads(body)["presets"][0]
        self.assertTrue(saved["saved"])
        self.assertEqual(saved["pool"], payload["pool"])
        self.assertEqual(sum(stock["weight"] for stock in saved["pool"]), 0.8)
        self.assertEqual(self.http("/api/pools", payload)[0], 409)
        changed = {**payload, "pool": [{"ticker": "c", "name": "新资产", "weight": 0.3}]}
        self.assertEqual(self.http("/api/pools", {**changed, "overwrite": True})[0], 200)
        restarted = WebApplication(self.root)
        try:
            pools = restarted.configuration()["presets"]
            self.assertEqual(len(pools), 1)
            self.assertEqual(pools[0]["pool"], [{"ticker": "C", "name": "新资产", "weight": 0.3}])
        finally:
            restarted.close()
        self.assertEqual(self.app.jobs, {})  # Saving a pool never submits a backtest.

    def test_pool_validation_authentication_and_builtin_protection(self):
        payload = {"name": "组合", "pool": request_data()["pool"]}
        for headers in ({"X-Local-Token": "wrong"}, {"Origin": "https://example.com"}, {"Host": "example.com"}):
            self.assertEqual(self.http("/api/pools", payload, headers)[0], 403)
        for update in ({"name": " "}, {"name": "x" * 81}, {"pool": []},
                       {"pool": [{"ticker": "A", "weight": -1}]},
                       {"pool": [{"ticker": "A", "weight": 0.8}, {"ticker": "A", "weight": 0.1}]},
                       {"pool": [{"ticker": "A", "weight": 1.1}]}):
            with self.subTest(update=update):
                self.assertEqual(self.http("/api/pools", {**payload, **update})[0], 400)
        self.assertFalse(self.app.pools_path.exists())
        directory = self.root / "configs/pools"
        directory.mkdir(parents=True)
        (directory / "example.json").write_text('{"A":"资产甲"}')
        self.assertEqual(self.http("/api/pools", {**payload, "name": "example", "overwrite": True})[0], 409)
        self.assertEqual(self.app.configuration()["presets"][0]["stocks"], {"A": "资产甲"})

    def test_corrupt_pool_file_is_not_overwritten(self):
        self.app.pools_path.parent.mkdir(parents=True)
        self.app.pools_path.write_text("invalid json")
        status, _, body = self.http("/api/pools", {"name": "组合", "pool": request_data()["pool"]})
        self.assertEqual(status, 400)
        self.assertIn("原文件未被覆盖", json.loads(body)["error"])
        self.assertEqual(self.app.pools_path.read_text(), "invalid json")

    def test_page_static_assets_and_connection_config(self):
        status, headers, body = self.http("/")
        self.assertEqual(status, 200)
        self.assertIn("策略回测".encode(), body)
        self.assertIn("Content-Security-Policy", headers)
        self.assertEqual(headers["Cache-Control"], "no-store")
        import re
        assets = re.findall(r'(?:src|href)="(\./assets/[^" ]+)"', body.decode())
        self.assertEqual(len(assets), 2)
        for asset in [url.removeprefix(".") for url in assets]:
            self.assertEqual(self.http(asset)[0], 200)
        status, _, body = self.http("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["token"], self.app.token)
        self.assertEqual(json.loads(body)["capabilities"]["research_version"], 1)
        self.assertEqual(json.loads(body)["capabilities"]["dca_version"], 1)
        self.assertEqual(json.loads(body)["capabilities"]["ma_independent_version"], 1)
        self.assertEqual(json.loads(body)["capabilities"]["ma_contributions_version"], 1)
        self.assertEqual(json.loads(body)["capabilities"]["ma_entry_budget_version"], 1)

    def test_frontend_missing_build_and_asset_path_boundaries(self):
        frontend = self.root / "frontend"
        with patch("scripts.web.STATIC", frontend):
            self.assertEqual(self.http("/")[0], 503)
            self.assertEqual(self.http("/api/config")[0], 200)
            (frontend / "assets").mkdir(parents=True)
            (frontend / "index.html").write_text("<!doctype html><title>test</title>")
            (frontend / "assets/app.js").write_text("export {}")
            secret = self.root / "private.js"
            secret.write_text("private data")
            (frontend / "assets/linked.js").symlink_to(secret)
            self.assertEqual(self.http("/assets/app.js")[0], 200)
            for asset in ("/assets/linked.js", "/assets/../../private.js", "/assets/missing.js"):
                self.assertEqual(self.http(asset)[0], 404)

    def test_background_run_uses_real_engine_and_exports_all_results(self):
        run_id = self.complete_run()
        status, _, body = self.http(f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        detail = json.loads(body)
        self.assertEqual(
            set(detail["results"]), {"buy_hold", "ma_band", "fixed_weight"}
        )
        self.assertEqual(len(detail["results"]["buy_hold"]["curve"]), 8)
        expected = BacktestEngine(
            StockPool({"A": "资产甲", "B": "资产乙"}), BacktestConfig(1000)
        ).run(prices(["A", "B"]), BuyAndHold({"A": 0.6, "B": 0.2}))
        self.assertEqual(
            detail["results"]["buy_hold"]["summary"]["final_equity"],
            expected.summary["final_equity"],
        )
        self.assertEqual(len(detail["results"]["buy_hold"]["tables"]["positions"]), 2)
        self.assertEqual(len(detail["comparison"]), 3)
        self.assertEqual(self.app.list_runs()["items"][0]["state"], "succeeded")
        status, headers, body = self.http(f"/api/runs/{run_id}/download.zip")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIn("buy_hold/fills.csv", archive.namelist())
            self.assertIn("comparison.csv", archive.namelist())
            self.assertIn("analysis/monthly_correlation.csv", archive.namelist())
        self.assertEqual(
            self.http(f"/api/runs/{run_id}/files/ma_band/trades.csv")[0], 200
        )

    def test_momentum_subperiods_and_perturbations_survive_http_and_zip(self):
        payload = {**request_data(), "strategies": ["ma_band", "cross_sectional_momentum"],
                   "buy_threshold": 0.03, "sell_threshold": 0.08,
                   "momentum_lookback": 2, "momentum_interval": 2, "momentum_top_n": 1,
                   "subperiod_count": 2, "sensitivity_enabled": True, "perturbation": 0.1}
        run_id = self.complete_run(payload)
        status, _, body = self.http(f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        detail = json.loads(body)
        self.assertEqual(detail["metadata"]["config"]["sell_threshold"], 0.08)
        for name in payload["strategies"]:
            result = detail["results"][name]
            self.assertEqual(len(result["tables"]["subperiods"]), 2)
            self.assertEqual(len(result["tables"]["sensitivity"]), 5)
            self.assertEqual(result["robustness"]["sensitivity"]["valid_variants"], 4)
            self.assertIn("subperiod_return_std", result["summary"])
            for file in ("subperiods.csv", "sensitivity.csv", "robustness.json"):
                self.assertEqual(self.http(f"/api/runs/{run_id}/files/{name}/{file}")[0], 200)
        with zipfile.ZipFile(io.BytesIO(self.http(f"/api/runs/{run_id}/download.zip")[2])) as archive:
            self.assertIn("cross_sectional_momentum/sensitivity.csv", archive.namelist())
            self.assertIn("ma_band/robustness.json", archive.namelist())
        self.assertEqual(self.http("/api/runs", {**payload, "momentum_top_n": 3})[0], 400)
        # The split cannot create one-day runs; report a failed task instead of silently changing the count.
        bad = self.app.submit({**payload, "subperiod_count": 5})["id"]
        deadline = time.monotonic() + 5
        while self.app.job_status(bad)["state"] in ("queued", "running") and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.app.job_status(bad)["state"], "failed")
        self.assertIn("至少需 2 日", self.app.job_status(bad)["message"])

    def test_dca_contributions_metrics_and_exports(self):
        payload = {**request_data(), "strategies": ["buy_hold", "dca"], "dca_amount": 100,
                   "dca_frequency": "each_observation", "subperiod_count": 2}
        run_id = self.complete_run(payload)
        status, _, body = self.http(f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        result = json.loads(body)["results"]["dca"]
        self.assertEqual(result["summary"]["total_contributed"], 1700)
        self.assertEqual(result["summary"]["return_method"], "time_weighted")
        self.assertAlmostEqual(result["summary"]["total_pnl"], result["summary"]["final_equity"] - 1700)
        self.assertEqual(len(result["tables"]["contributions"]), 8)
        self.assertEqual(len(result["tables"]["subperiods"]), 2)
        self.assertTrue(all(row["side"] == "buy" for row in result["tables"]["fills"]))
        self.assertEqual(self.http(f"/api/runs/{run_id}/files/dca/contributions.csv")[0], 200)
        with zipfile.ZipFile(io.BytesIO(self.http(f"/api/runs/{run_id}/download.zip")[2])) as archive:
            self.assertIn("dca/contributions.csv", archive.namelist())

    def test_ma_independent_orders_and_research_survive_http(self):
        payload = {**request_data(), "strategies": ["ma_band"], "ma_window": 2,
                   "ma_trade_mode": "independent", "ma_buy_amount": 100,
                   "ma_sell_fraction": 0.5, "subperiod_count": 2, "sensitivity_enabled": True}
        run_id = self.complete_run(payload)
        detail = json.loads(self.http(f"/api/runs/{run_id}")[2])
        result = detail["results"]["ma_band"]
        self.assertEqual(result["summary"]["ma_trade_mode"], "independent")
        self.assertEqual(detail["metadata"]["config"]["ma_sell_fraction"], 0.5)
        fills = [row for row in result["tables"]["fills"] if row["ticker"] == "A"]
        self.assertEqual([row["side"] for row in fills[:4]], ["buy", "buy", "sell", "sell"])
        self.assertTrue(any(row["order_type"] == "signal_buy_budget" for row in result["tables"]["orders"]))
        self.assertTrue(any(row["order_type"] == "signal_sell_fraction" for row in result["tables"]["orders"]))
        self.assertEqual(len(result["tables"]["sensitivity"]), 5)
        self.assertEqual(self.http(f"/api/runs/{run_id}/files/ma_band/orders.csv")[0], 200)
        self.assertEqual(self.http("/api/runs", {**payload, "ma_sell_fraction": 1.1})[0], 400)

    def test_ma_auto_contribution_reports_real_principal_and_cash_flow_exports(self):
        payload = {**request_data(), "strategies": ["ma_band"], "initial_cash": 50, "ma_window": 2,
                   "ma_trade_mode": "independent", "ma_buy_amount": 100, "ma_sell_fraction": 0.5,
                   "ma_funding_mode": "auto_contribute", "subperiod_count": 2}
        run_id = self.complete_run(payload)
        result = json.loads(self.http(f"/api/runs/{run_id}")[2])["results"]["ma_band"]
        self.assertGreater(result["summary"]["total_contributed"], 50)
        self.assertEqual(result["summary"]["return_method"], "time_weighted")
        self.assertEqual(result["summary"]["ma_funding_mode"], "auto_contribute")
        self.assertTrue(any(row["kind"] == "signal_top_up" for row in result["tables"]["contributions"]))
        self.assertAlmostEqual(result["summary"]["total_pnl"], result["summary"]["final_equity"] - result["summary"]["total_contributed"])
        self.assertEqual(self.http(f"/api/runs/{run_id}/files/ma_band/contributions.csv")[0], 200)
        with zipfile.ZipFile(io.BytesIO(self.http(f"/api/runs/{run_id}/download.zip")[2])) as archive:
            self.assertIn("ma_band/contributions.csv", archive.namelist())

    def test_ma_first_entries_and_cash_plus_extra_config_and_reports(self):
        payload = {**request_data(), "strategies": ["ma_band"], "ma_window": 2,
                   "ma_trade_mode": "independent", "ma_buy_first_only": True, "ma_sell_first_only": True,
                   "ma_buy_budget_mode": "cash_plus_extra", "ma_extra_amount": 200,
                   "subperiod_count": 2, "sensitivity_enabled": True}
        run_id = self.complete_run(payload)
        detail = json.loads(self.http(f"/api/runs/{run_id}")[2])
        result = detail["results"]["ma_band"]
        summary = result["summary"]
        self.assertTrue(summary["ma_buy_first_only"])
        self.assertTrue(summary["ma_sell_first_only"])
        self.assertEqual(summary["ma_buy_budget_mode"], "cash_plus_extra")
        self.assertEqual(detail["metadata"]["config"]["ma_extra_amount"], 200)
        first_buys = [row for row in result["tables"]["fills"] if row["side"] == "buy" and row["date"] == result["tables"]["fills"][0]["date"]]
        self.assertAlmostEqual(sum(row["notional"] + row["fee"] for row in first_buys), 1200)
        self.assertTrue(all(row["amount"] == 200 for row in result["tables"]["contributions"] if row["kind"] == "signal_extra"))
        self.assertEqual(len(result["tables"]["subperiods"]), 2)
        self.assertEqual(len(result["tables"]["sensitivity"]), 5)
        self.assertEqual(self.http(f"/api/runs/{run_id}/files/ma_band/contributions.csv")[0], 200)

    def test_invalid_payload_and_cross_site_requests_cannot_start_jobs(self):
        self.assertEqual(
            self.http("/api/runs", request_data(), {"X-Local-Token": "wrong"})[0], 403
        )
        self.assertEqual(
            self.http("/api/runs", request_data(), {"Origin": "https://example.com"})[
                0
            ],
            403,
        )
        self.assertEqual(
            self.http("/api/config", headers={"Host": "example.com"})[0], 403
        )
        invalid = request_data()
        invalid["pool"][0]["weight"] = 1.5
        self.assertEqual(self.http("/api/runs", invalid)[0], 400)
        self.assertEqual(self.app.jobs, {})
        for update in [
            {"pool": []},
            {"strategies": []},
            {"strategies": ["unknown"]},
            {"ma_window": 1.5},
            {"period": "bad"},
            {"initial_cash": float("inf")},
        ]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                normalize_request({**request_data(), **update})

    def test_failure_is_persisted_without_fake_results(self):
        def failing(*args, **kwargs):
            raise RuntimeError("缓存缺少股票：A")

        self.app.price_loader = failing
        run_id = self.app.submit(request_data())["id"]
        deadline = time.monotonic() + 5
        while (
            self.app.job_status(run_id)["state"] in ("queued", "running")
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertEqual(self.app.job_status(run_id)["state"], "failed")
        self.assertIn("缓存缺少", self.app.job_status(run_id)["message"])
        self.assertEqual(self.app.list_runs()["items"][0]["state"], "failed")
        self.assertEqual(self.http(f"/api/runs/{run_id}")[0], 404)

    def test_restart_marks_unfinished_job_as_interrupted(self):
        path = self.root / "outputs/web_backtest/unfinished"
        path.mkdir(parents=True)
        write_json(
            path / "status.json", {"id": "web_backtest__unfinished", "state": "running"}
        )
        self.assertEqual(
            self.app.job_status("web_backtest__unfinished")["state"], "interrupted"
        )

    def test_download_paths_and_symlinks_are_restricted(self):
        run_id = self.complete_run()
        path = self.app.run_path(run_id)
        secret = self.root / "private.json"
        secret.write_text('{"secret": true}')
        (path / "ma_band/summary.json").unlink()
        (path / "ma_band/summary.json").symlink_to(secret)
        for filename in ["../../private.json", "ma_band/summary.json", "private.json"]:
            with self.subTest(filename=filename), self.assertRaises(FileNotFoundError):
                self.app.result_file(run_id, filename)
        self.assertEqual(
            self.http("/api/runs/web_backtest__../files/private.json")[0], 404
        )
        with zipfile.ZipFile(io.BytesIO(self.app.zip_results(run_id))) as archive:
            self.assertNotIn("ma_band/summary.json", archive.namelist())
        status, _, body = self.http(f"/api/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertNotIn('"secret"', body.decode())
        (path / "run_config.json").unlink()
        (path / "run_config.json").symlink_to(secret)
        self.assertEqual(self.http(f"/api/runs/{run_id}")[0], 404)

    def test_cache_listing_is_read_only_and_handles_missing_cache(self):
        self.assertEqual(self.app.cache_info(), {"items": []})
        self.assertFalse(self.app.cache_path.exists())
        with sqlite3.connect(self.app.cache_path) as db:
            market_data._initialize(db)
            db.execute(
                "INSERT INTO metadata VALUES (?,?,?,?,?,?,?,?)",
                (
                    market_data.DATASET,
                    "A",
                    "2024-01-03T00:00:00+00:00",
                    "2024-01-01",
                    "2024-01-03",
                    3,
                    "test",
                    1,
                ),
            )
        self.assertEqual(self.app.cache_info()["items"][0]["ticker"], "A")


if __name__ == "__main__":
    unittest.main()

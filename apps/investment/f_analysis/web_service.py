"""本机网页的应用层：校验配置、后台任务及已有结果读取。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import io
import json
import math
import os
import tempfile
from pathlib import Path
import re
import secrets
import sqlite3
from threading import Lock
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import (
    BacktestConfig,
    BacktestEngine,
    BuyAndHold,
    FixedWeightRebalance,
    MABand,
    StockPool,
)
from .analytics import correlation_analysis
from .reporting import compare_results, plot_comparison, save_result
from .strategies import FREQUENCIES, allocation
from scripts import market_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRATEGIES = {
    "buy_hold": "买入持有",
    "ma_band": "MA 均线策略",
    "fixed_weight": "固定权重再平衡",
}
CATEGORIES = ("web_backtest", "portfolio_backtest", "single_stock_backtest")
FILES = {
    "summary.json",
    "daily_history.csv",
    "positions.csv",
    "fills.csv",
    "trades.csv",
    "orders.csv",
    "monthly_returns.csv",
    "yearly_returns.csv",
}
ROOT_FILES = {
    "comparison.csv",
    "comparison.png",
    "backtest.png",
    "run_config.json",
    "status.json",
}


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temp.replace(path)


def records(frame):
    # pandas 负责将缺失值/非有限数统一变为 JSON null。
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def read_csv(path):
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def normalize_request(data):
    if not isinstance(data, dict):
        raise ValueError("请求必须是 JSON 对象")
    rows = data.get("pool")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError("股票池需要 1～50 只股票")
    stocks, weights = {}, {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("ticker"), str):
            raise ValueError("请填写股票代码")
        ticker = row["ticker"].strip().upper()
        if (
            not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,31}", ticker)
            or ticker in stocks
        ):
            raise ValueError("股票代码无效或重复，请使用如 600036.SS 的 Yahoo 代码")
        stocks[ticker] = str(row.get("name") or ticker).strip()[:80]
        try:
            weights[ticker] = float(row["weight"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("每只股票都需要有效的配置权重") from None
    pool = StockPool(stocks)
    weights = allocation(pool, weights)
    names = data.get("strategies", ["buy_hold", "ma_band"])
    if (
        not isinstance(names, list)
        or not names
        or any(not isinstance(n, str) or n not in STRATEGIES for n in names)
    ):
        raise ValueError("请至少选择一种有效策略")
    names = list(dict.fromkeys(names))
    period = data.get("period", "5y")
    if not isinstance(period, str) or not re.fullmatch(
        r"max|ytd|[1-9]\d{0,2}(?:d|wk|mo|y)", period
    ):
        raise ValueError("分析范围需为 max、ytd 或 3y、6mo 等格式")
    try:
        initial_cash = float(data.get("initial_cash", 100_000))
        fee_rate = float(data.get("fee_rate", 0))
        raw_window = data.get("ma_window", 30)
        window = int(raw_window)
        if (
            isinstance(raw_window, bool)
            or float(raw_window) != window
            or not 1 <= window <= 5000
        ):
            raise ValueError()
        threshold = float(data.get("threshold", 0.05))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("资金、费率、均线窗口及偏离比例格式无效") from None
    BacktestConfig(initial_cash, fee_rate)
    MABand(window, threshold, weights)
    frequency = data.get("rebalance_frequency", "monthly")
    if frequency not in FREQUENCIES:
        raise ValueError("请选择有效的再平衡频率")
    mode = data.get("data_mode", "cache")
    if mode not in ("cache", "refresh", "offline"):
        raise ValueError("请选择有效的行情模式")
    return {
        "pool": stocks,
        "weights": weights,
        "strategies": names,
        "period": period,
        "initial_cash": initial_cash,
        "fee_rate": fee_rate,
        "ma_window": window,
        "threshold": threshold,
        "rebalance_frequency": frequency,
        "data_mode": mode,
    }


class PoolConflict(ValueError):
    pass


class WebApplication:
    def __init__(
        self, project_root=PROJECT_ROOT, *, price_loader=None, cache_path=None
    ):
        self.root = Path(project_root).resolve()
        self.outputs = self.root / "outputs"
        self.cache_path = Path(cache_path or market_data.DEFAULT_CACHE_PATH)
        self.price_loader = price_loader or market_data.get_prices
        self.token = secrets.token_urlsafe(32)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtest")
        self.lock = Lock()
        self.jobs = {}
        self.pools_lock = Lock()
        self.pools_path = self.root / "data/stock_pools.json"

    def close(self):
        self.executor.shutdown(wait=True)

    def _saved_pools(self):
        try:
            pools = json.loads(self.pools_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            raise ValueError("已保存的股票池文件无法读取，请检查 data/stock_pools.json；原文件未被覆盖") from exc
        if not isinstance(pools, list):
            raise ValueError("股票池文件格式无效；原文件未被覆盖")
        for item in pools:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ValueError("股票池文件格式无效；原文件未被覆盖")
            normalize_request({"pool": item.get("pool")})
        return pools

    def pool_presets(self):
        presets = []
        for path in sorted((self.root / "configs/pools").glob("*.json")):
            pool = read_json(path)
            if isinstance(pool, dict) and pool:
                presets.append({"name": path.stem, "stocks": pool})
        with self.pools_lock:
            presets.extend({**item, "saved": True} for item in self._saved_pools())
        return presets

    def save_pool(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            raise ValueError("请填写股票池名称")
        name = data["name"].strip()
        if not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
            raise ValueError("股票池名称需为 1～80 个字符，不能包含控制字符")
        config = normalize_request({"pool": data.get("pool")})
        item = {"name": name, "pool": [
            {"ticker": ticker, "name": title, "weight": config["weights"][ticker]}
            for ticker, title in config["pool"].items()
        ]}
        if any(path.stem == name for path in (self.root / "configs/pools").glob("*.json")):
            raise PoolConflict("此名称属于内置股票池，请使用其他名称")
        with self.pools_lock:
            pools = self._saved_pools()
            existing = next((i for i, pool in enumerate(pools) if pool["name"] == name), None)
            if existing is not None:
                if data.get("overwrite") is not True:
                    raise PoolConflict("此名称已存在，请重新载入后确认覆盖，或使用其他名称")
                pools[existing] = item
            else:
                pools.append(item)
            self.pools_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.pools_path.parent, delete=False) as file:
                    temporary = Path(file.name)
                    json.dump(pools, file, ensure_ascii=False, indent=2, allow_nan=False)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, self.pools_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return {"name": name, "presets": self.pool_presets()}

    def configuration(self):
        return {
            "token": self.token,
            "strategies": STRATEGIES,
            "presets": self.pool_presets(),
            "defaults": {
                "pool": [
                    {"ticker": "600036.SS", "name": "招商银行", "weight": 0.5},
                    {"ticker": "002594.SZ", "name": "比亚迪", "weight": 0.5},
                ],
                "strategies": ["buy_hold", "ma_band"],
                "period": "5y",
                "initial_cash": 100000,
                "fee_rate": 0,
                "ma_window": 30,
                "threshold": 0.05,
                "rebalance_frequency": "monthly",
                "data_mode": "cache",
            },
        }

    def cache_info(self):
        if not self.cache_path.is_file():
            return {"items": []}
        with closing(
            sqlite3.connect(
                self.cache_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
            )
        ) as db:
            try:
                cursor = db.execute(
                    "SELECT ticker,start_date,end_date,row_count,fetched_at FROM metadata WHERE dataset=? ORDER BY ticker",
                    (market_data.DATASET,),
                )
                items = [
                    dict(zip([c[0] for c in cursor.description], row))
                    for row in cursor.fetchall()
                ]
            except sqlite3.OperationalError as exc:
                raise ValueError("行情缓存无法读取，请先通过回测重新下载行情") from exc
        return {"items": items}

    def run_path(self, run_id):
        if not isinstance(run_id, str) or "__" not in run_id:
            raise FileNotFoundError("运行记录不存在")
        category, folder = run_id.split("__", 1)
        if category not in CATEGORIES or not re.fullmatch(r"[A-Za-z0-9_\-]+", folder):
            raise FileNotFoundError("运行记录不存在")
        path = (self.outputs / category / folder).resolve()
        if not path.is_relative_to(self.outputs.resolve()) or not path.is_dir():
            raise FileNotFoundError("运行记录不存在")
        return path

    def list_runs(self):
        items = []
        for category in CATEGORIES:
            for path in (self.outputs / category).glob("*/run_config.json"):
                if not path.resolve().is_relative_to(self.outputs.resolve()):
                    continue
                metadata = read_json(path, {})
                if not isinstance(metadata, dict):
                    continue
                config = metadata.get("config", {})
                run_id = f"{category}__{path.parent.name}"
                if not re.fullmatch(r"[A-Za-z0-9_\-]+", path.parent.name):
                    continue
                status = self.job_status(run_id, allow_missing=True)
                if status:
                    state = status["state"]
                elif (path.parent / "comparison.csv").is_file():
                    state = "succeeded"
                else:
                    continue
                items.append(
                    {
                        "id": run_id,
                        "created_at": metadata.get("created_at", ""),
                        "state": state,
                        "config": config,
                        "source": category,
                        "message": status.get("message", "") if status else "",
                    }
                )
        return {
            "items": sorted(items, key=lambda item: item["created_at"], reverse=True)[
                :100
            ]
        }

    def _set_job(self, run_id, **updates):
        with self.lock:
            self.jobs[run_id].update(updates)
            snapshot = dict(self.jobs[run_id])
        write_json(self.run_path(run_id) / "status.json", snapshot)

    def job_status(self, run_id, allow_missing=False):
        with self.lock:
            snapshot = self.jobs.get(run_id)
            if snapshot:
                return dict(snapshot)
        directory = self.run_path(run_id)
        status_file = directory / "status.json"
        snapshot = (
            read_json(status_file)
            if status_file.resolve().is_relative_to(directory)
            else None
        )
        if not isinstance(snapshot, dict):
            snapshot = None
        if snapshot and snapshot.get("state") in ("queued", "running"):
            snapshot.update(
                state="interrupted", message="服务已重启，此任务未完成，请重新运行"
            )
        if snapshot is None and not allow_missing:
            raise FileNotFoundError("任务不存在")
        return snapshot

    def submit(self, data):
        config = normalize_request(data)
        with self.lock:
            if (
                sum(job["state"] in ("queued", "running") for job in self.jobs.values())
                >= 4
            ):
                raise ValueError("等待中的任务较多，请稍后再试")
        folder = (
            datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-" + secrets.token_hex(3)
        )
        run_id = "web_backtest__" + folder
        path = self.outputs / "web_backtest" / folder
        path.mkdir(parents=True)
        write_json(
            path / "run_config.json",
            {
                "script": "web_backtest",
                "created_at": datetime.now().astimezone().isoformat(),
                "config": config,
            },
        )
        with self.lock:
            self.jobs[run_id] = {
                "id": run_id,
                "state": "queued",
                "progress": 0,
                "message": "等待运行",
            }
        self._set_job(run_id)
        self.executor.submit(self._run, run_id, config)
        return {"id": run_id}

    def _run(self, run_id, config):
        try:
            path = self.run_path(run_id)
            self._set_job(
                run_id, state="running", progress=8, message="读取缓存或下载行情…"
            )
            pool = StockPool(config["pool"])
            prices = self.price_loader(
                pool.tickers,
                period=config["period"],
                refresh=config["data_mode"] == "refresh",
                offline=config["data_mode"] == "offline",
                cache_path=self.cache_path,
                report_path=path / "run_config.json",
            )
            engine = BacktestEngine(
                pool, BacktestConfig(config["initial_cash"], config["fee_rate"])
            )
            results = {}
            for i, name in enumerate(config["strategies"]):
                self._set_job(
                    run_id,
                    progress=25 + int(50 * i / len(config["strategies"])),
                    message=f"正在回测：{STRATEGIES[name]}…",
                )
                if name == "buy_hold":
                    strategy = BuyAndHold(config["weights"])
                elif name == "ma_band":
                    strategy = MABand(
                        config["ma_window"], config["threshold"], config["weights"]
                    )
                else:
                    strategy = FixedWeightRebalance(
                        config["weights"], config["rebalance_frequency"]
                    )
                result = engine.run(prices, strategy)
                result.summary["weights"] = config["weights"]
                result.summary["ma_window"] = (
                    config["ma_window"] if name == "ma_band" else None
                )
                result.summary["threshold"] = (
                    config["threshold"] if name == "ma_band" else None
                )
                results[name] = result
                save_result(path / name, result)
            self._set_job(run_id, progress=85, message="生成对比报告与图表…")
            compare_results(results).to_csv(path / "comparison.csv", index=False)
            analysis = path / "analysis"
            analysis.mkdir()
            for rule, name in [(None, "daily"), ("ME", "monthly")]:
                _, corr = correlation_analysis(prices, rule)
                corr.to_csv(analysis / f"{name}_correlation.csv")
            fig = plot_comparison(results, path / "comparison.png")
            plt.close(fig)
            self._set_job(run_id, state="succeeded", progress=100, message="回测完成")
        except Exception as exc:
            self._set_job(
                run_id, state="failed", message=str(exc) or type(exc).__name__
            )
        finally:
            plt.close("all")

    def run_details(self, run_id):
        path = self.run_path(run_id)
        status = self.job_status(run_id, allow_missing=True)
        if status and status.get("state") != "succeeded":
            raise FileNotFoundError("本次运行尚未成功完成，请先查看运行状态")
        metadata = read_json(self.result_file(run_id, "run_config.json"), {})
        results = {}
        for name in STRATEGIES:
            directory = path / name
            if not (directory / "summary.json").resolve().is_relative_to(path):
                continue
            summary = read_json(directory / "summary.json")
            if not summary:
                continue
            history_path = directory / "daily_history.csv"
            history = (
                read_csv(history_path)
                if history_path.resolve().is_relative_to(path)
                else pd.DataFrame()
            )
            date_column = next(
                (col for col in ("date", "Date") if col in history), None
            )
            if date_column and not history.empty:
                history = history.rename(columns={date_column: "date"})
                columns = [
                    col
                    for col in (
                        "date",
                        "equity",
                        "total_return",
                        "drawdown",
                        "cumulative_pnl",
                    )
                    if col in history
                ]
                # 图表最多约 2500 点；绩效与下载文件始终使用完整数据。
                step = max(1, math.ceil(len(history) / 2500))
                curve = history[columns].iloc[::step]
                if curve.index[-1] != history.index[-1]:
                    curve = pd.concat([curve, history[columns].tail(1)])
            else:
                curve = pd.DataFrame()
            tables, counts = {}, {}
            for file in (
                "fills",
                "trades",
                "monthly_returns",
                "yearly_returns",
                "positions",
                "orders",
            ):
                table_path = directory / f"{file}.csv"
                table = (
                    read_csv(table_path)
                    if table_path.resolve().is_relative_to(path)
                    else pd.DataFrame()
                )
                if file == "positions" and not table.empty and "date" in table:
                    table = table.loc[table["date"] == table["date"].iloc[-1]]
                counts[file] = len(table)
                tables[file] = records(table.tail(500))
            results[name] = {
                "summary": summary,
                "curve": records(curve),
                "tables": tables,
                "counts": counts,
            }
        if not results:
            raise FileNotFoundError("本次运行尚未生成结果")
        corr_path = path / "analysis/monthly_correlation.csv"
        corr = (
            read_csv(corr_path)
            if corr_path.resolve().is_relative_to(path)
            else pd.DataFrame()
        )
        correlation = None
        if not corr.empty:
            correlation = {"columns": list(corr.columns[1:]), "rows": records(corr)}
        return {
            "id": run_id,
            "metadata": metadata,
            "results": results,
            "comparison": records(read_csv(self.result_file(run_id, "comparison.csv"))),
            "correlation": correlation,
        }

    def result_file(self, run_id, filename):
        path = self.run_path(run_id)
        parts = Path(filename).parts
        allowed = (
            (len(parts) == 1 and filename in ROOT_FILES)
            or (len(parts) == 2 and parts[0] in STRATEGIES and parts[1] in FILES)
            or (
                len(parts) == 2
                and parts[0] == "analysis"
                and parts[1] in ("daily_correlation.csv", "monthly_correlation.csv")
            )
        )
        candidate = (path / filename).resolve()
        if not allowed or not candidate.is_relative_to(path) or not candidate.is_file():
            raise FileNotFoundError("文件不存在")
        return candidate

    def zip_results(self, run_id):
        path = self.run_path(run_id)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in path.rglob("*"):
                if not file.is_file():
                    continue
                relative = file.relative_to(path).as_posix()
                try:
                    valid = self.result_file(run_id, relative)
                except FileNotFoundError:
                    continue
                archive.write(valid, relative)
        return output.getvalue()

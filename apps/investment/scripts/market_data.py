"""按标的共享的复权日线缓存；只在缺失或显式刷新时访问 Yahoo。"""

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data/cache/market_data.sqlite3"
)
SCHEMA_VERSION = 1
DATASET = "yahoo:1d:auto_adjust=true:v1"


def _period_start(period, today):
    if period == "max":
        return None
    if period == "ytd":
        return today.replace(month=1, day=1)
    match = re.fullmatch(r"([1-9]\d*)(d|wk|mo|y)", period)
    if not match:
        raise ValueError("period 必须是 max、ytd 或正整数加 d/wk/mo/y（如 3y）")
    count, unit = int(match[1]), match[2]
    units = {"d": "days", "wk": "weeks", "mo": "months", "y": "years"}
    return today - pd.DateOffset(**{units[unit]: count})


def _initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS prices (
            dataset TEXT NOT NULL, ticker TEXT NOT NULL, date TEXT NOT NULL,
            close REAL NOT NULL, PRIMARY KEY (dataset, ticker, date)
        );
        CREATE TABLE IF NOT EXISTS metadata (
            dataset TEXT NOT NULL, ticker TEXT NOT NULL, fetched_at TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL, row_count INTEGER NOT NULL,
            library_version TEXT NOT NULL, schema_version INTEGER NOT NULL,
            PRIMARY KEY (dataset, ticker)
        );
    """)


def _read(db, ticker):
    row = db.execute(
        "SELECT fetched_at, start_date, end_date, row_count, library_version, schema_version "
        "FROM metadata WHERE dataset=? AND ticker=?",
        (DATASET, ticker),
    ).fetchone()
    if row is None:
        return None
    rows = db.execute(
        "SELECT date, close FROM prices WHERE dataset=? AND ticker=? ORDER BY date",
        (DATASET, ticker),
    ).fetchall()
    if not rows or len(rows) != row[3] or row[5] != SCHEMA_VERSION:
        raise RuntimeError(f"{ticker} 缓存不完整或版本不兼容，请使用 --refresh-data")
    series = pd.Series(
        [r[1] for r in rows],
        index=pd.to_datetime([r[0] for r in rows]),
        name=ticker,
    )
    fields = [
        "fetched_at",
        "start_date",
        "end_date",
        "row_count",
        "yfinance_version",
        "schema_version",
    ]
    info = dict(zip(fields, row))
    return series, info


def _download(tickers):
    try:
        data = yf.download(
            tickers,
            period="max",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if data is None or data.empty:
            raise ValueError("返回空行情")
        close = data["Close"]
        if isinstance(close, pd.Series):
            if len(tickers) != 1:
                raise ValueError("返回行情缺少标的列")
            close = close.to_frame(tickers[0])
        result = {}
        for ticker in tickers:
            series = pd.to_numeric(close[ticker], errors="raise").dropna().copy()
            series.index = pd.DatetimeIndex(series.index).tz_localize(None).normalize()
            series = series[~series.index.duplicated(keep="last")].sort_index()
            if (
                series.empty
                or series.index.hasnans
                or not np.isfinite(series.to_numpy()).all()
                or (series <= 0).any()
            ):
                raise ValueError(f"{ticker} 返回空行情或无效价格")
            result[ticker] = series.rename(ticker)
        return result
    except Exception as exc:
        raise RuntimeError(f"行情下载失败，旧缓存保持不变：{exc}") from exc


def _write(db, downloaded):
    fetched_at = datetime.now(timezone.utc).isoformat()
    # 整批验证后才开始事务，任一标的失败都不会覆盖已有历史。
    with db:
        for ticker, series in downloaded.items():
            db.execute(
                "DELETE FROM prices WHERE dataset=? AND ticker=?", (DATASET, ticker)
            )
            db.executemany(
                "INSERT INTO prices VALUES (?, ?, ?, ?)",
                [
                    (DATASET, ticker, date.date().isoformat(), float(value))
                    for date, value in series.items()
                ],
            )
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    DATASET,
                    ticker,
                    fetched_at,
                    series.index[0].date().isoformat(),
                    series.index[-1].date().isoformat(),
                    len(series),
                    yf.__version__,
                    SCHEMA_VERSION,
                ),
            )


def get_prices(
    tickers,
    period="max",
    *,
    refresh=False,
    offline=False,
    cache_path=None,
    report_path=None,
    as_of=None,
):
    """返回未跨标的对齐/填充的 Close 表；period 按分析日而非缓存末日截取。

    as_of 仅用于确定本地截取窗口；不会向行情服务请求历史时点快照。
    """
    tickers = list(dict.fromkeys(tickers))
    # TODO(yzt): t.strip()?
    if not tickers or any(not isinstance(t, str) or not t.strip() for t in tickers):
        raise ValueError("至少需要一个有效标的代码")
    if refresh and offline:
        raise ValueError("refresh 与 offline 不能同时使用")

    analysis_date = (
        as_of if as_of is not None else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    )
    today = pd.Timestamp(analysis_date).tz_localize(None).normalize()
    start = _period_start(period, today)
    path = Path(cache_path) if cache_path is not None else DEFAULT_CACHE_PATH
    path = path.resolve()
    if offline and not path.exists():
        raise RuntimeError(f"离线模式缺少行情缓存：{', '.join(tickers)}；请先联网运行")

    path.parent.mkdir(parents=True, exist_ok=True)
    # TODO(yzt): closing?
    with closing(sqlite3.connect(path, timeout=30)) as db:
        _initialize(db)
        cached = {} if refresh else {t: _read(db, t) for t in tickers}
        missing = [t for t in tickers if cached.get(t) is None]
        if offline and missing:
            raise RuntimeError(
                f"离线模式缺少行情缓存：{', '.join(missing)}；请先联网运行"
            )
        if missing:
            print(f"下载完整历史: {', '.join(missing)}")
            _write(db, _download(missing))
            for ticker in missing:
                cached[ticker] = _read(db, ticker)

        selected, records = [], []
        for ticker in tickers:
            series, info = cached[ticker]
            series = series.loc[series.index <= today]
            if start is not None:
                series = series.loc[series.index >= start]
            if series.empty:
                raise RuntimeError(
                    f"{ticker} 在 {period} 范围内没有行情，缓存截至 "
                    f"{info['end_date']}；请刷新或扩大分析范围"
                )
            source = "download" if ticker in missing else "cache"
            print(
                f"{ticker}: {'下载' if source == 'download' else '缓存'}，"
                f"行情截至 {info['end_date']}，缓存更新于 {info['fetched_at']}"
            )
            selected.append(series)
            records.append(
                {
                    "ticker": ticker,
                    "source": source,
                    **info,
                    "selected_start": series.index[0].date().isoformat(),
                    "selected_end": series.index[-1].date().isoformat(),
                }
            )
    prices = pd.concat(selected, axis=1).sort_index()
    prices.index.name = "Date"
    if report_path is not None:
        report_path = Path(report_path)
        metadata = json.loads(report_path.read_text(encoding="utf-8"))
        metadata["market_data"] = {
            "cache_path": str(path),
            "dataset": DATASET,
            "as_of": today.date().isoformat(),
            "period": period,
            "refresh": refresh,
            "offline": offline,
            "tickers": records,
        }
        report_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return prices

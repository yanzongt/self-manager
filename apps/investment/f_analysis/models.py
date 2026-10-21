"""股票池、回测配置及标准结果；不依赖行情服务。"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StockPool:
    """允许交易的股票集合，映射为 Yahoo 代码 -> 显示名称。"""

    stocks: Mapping[str, str]

    def __post_init__(self):
        if not isinstance(self.stocks, Mapping) or any(
            not isinstance(t, str) or not t.strip() for t in self.stocks
        ):
            raise ValueError("股票池必须是有效股票代码到名称的映射")
        cleaned = {str(t).strip().upper(): str(n) for t, n in self.stocks.items()}
        if (
            not cleaned
            or any(not t for t in cleaned)
            or len(cleaned) != len(self.stocks)
        ):
            raise ValueError("股票池不能为空，代码必须有效且不重复")
        object.__setattr__(self, "stocks", MappingProxyType(cleaned))

    @classmethod
    def from_tickers(cls, tickers):
        if isinstance(tickers, str):
            raise ValueError("股票代码应使用列表传入")
        tickers = list(tickers)
        if len(set(str(t).strip().upper() for t in tickers)) != len(tickers):
            raise ValueError("股票池代码不能重复")
        return cls({t: t for t in tickers})

    @property
    def tickers(self):
        return tuple(self.stocks)

    def select_prices(self, prices, *, allow_unquoted=False):
        if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.hasnans:
            raise ValueError("行情索引必须为有效日期")
        if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
            raise ValueError("行情日期必须升序且不能重复")
        if not prices.columns.is_unique or not set(self.tickers).issubset(
            prices.columns
        ):
            raise ValueError("行情缺少股票池标的或包含重复列")
        frame = prices.loc[:, list(self.tickers)].astype(float).copy()
        values = frame.to_numpy()
        if np.isinf(values).any() or (frame <= 0).any().any():
            raise ValueError("有效行情必须为有限正数")
        frame = frame.dropna(how="all")
        if len(frame) < 2 or (not allow_unquoted and frame.notna().sum().eq(0).any()):
            raise ValueError("至少需要两个行情日期，且每只股票至少有一个有效价格")
        return frame


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    fee_rate: float = 0.0

    def __post_init__(self):
        if not np.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("初始资金必须为有限正数")
        if not np.isfinite(self.fee_rate) or not 0 <= self.fee_rate < 1:
            raise ValueError("单边费率必须大于等于 0 且小于 1")


@dataclass(frozen=True)
class StrategyContext:
    date: pd.Timestamp
    history: pd.DataFrame  # 仅包含截至当前收盘的数据
    pool: StockPool
    cash: float
    equity: float
    quantities: Mapping[str, float]


@dataclass
class BacktestResult:
    history: pd.DataFrame
    positions: pd.DataFrame
    fills: pd.DataFrame
    trades: pd.DataFrame
    orders: pd.DataFrame
    summary: dict
    subperiods: pd.DataFrame = field(default_factory=pd.DataFrame)
    sensitivity: pd.DataFrame = field(default_factory=pd.DataFrame)
    robustness: dict = field(default_factory=dict)

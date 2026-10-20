"""策略只产生目标权重，不操作现金或计算成交数量。"""

from dataclasses import dataclass
from typing import Mapping, Protocol

import numpy as np
import pandas as pd

from .models import StockPool, StrategyContext


def validate_targets(targets, pool):
    targets = dict(targets)
    if not set(targets).issubset(pool.tickers):
        raise ValueError("目标权重包含股票池以外的代码")
    if any(not np.isfinite(w) or w < 0 or w > 1 for w in targets.values()):
        raise ValueError("目标权重必须为 0 到 1 之间的有限数")
    if sum(targets.values()) > 1 + 1e-12:
        raise ValueError("目标权重之和不能大于 1（不支持杠杆）")
    return targets


def allocation(pool, weights):
    if weights is None:
        return {ticker: 1 / len(pool.tickers) for ticker in pool.tickers}
    checked = validate_targets(weights, pool)
    return {ticker: checked.get(ticker, 0.0) for ticker in pool.tickers}


class Strategy(Protocol):
    name: str

    def initial_targets(self, pool: StockPool): ...
    def scheduled_targets(self, date, previous_date, pool: StockPool): ...
    def on_close(self, context: StrategyContext): ...


class BaseStrategy:
    """返回 None 表示不调整；映射只调整列出的标的，目标 0 表示清仓。"""

    name = "custom"

    def initial_targets(self, pool):
        return None

    def scheduled_targets(self, date, previous_date, pool):
        return None

    def on_close(self, context):
        return None


@dataclass(frozen=True)
class BuyAndHold(BaseStrategy):
    weights: Mapping[str, float] | None = None
    name = "buy_hold"

    def initial_targets(self, pool):
        return allocation(pool, self.weights)


FREQUENCIES = ("monthly", "quarterly", "semiannual", "annual", "each_observation")


def _period_key(date, frequency):
    if frequency == "monthly":
        return date.year, date.month
    if frequency == "quarterly":
        return date.year, (date.month - 1) // 3
    if frequency == "semiannual":
        return date.year, (date.month - 1) // 6
    if frequency == "annual":
        return date.year
    return date


@dataclass(frozen=True)
class FixedWeightRebalance(BuyAndHold):
    frequency: str = "monthly"
    name = "fixed_weight"

    def __post_init__(self):
        if self.frequency not in FREQUENCIES:
            raise ValueError(f"未知再平衡频率: {self.frequency}")

    def scheduled_targets(self, date, previous_date, pool):
        # 预先确定的日历计划，不读取当日收盘来决定是否交易。
        if previous_date is not None and _period_key(
            date, self.frequency
        ) != _period_key(previous_date, self.frequency):
            return allocation(pool, self.weights)
        return None


def ma_band_signals(close, window=30, threshold=0.05):
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("MA 窗口必须为正整数")
    if not np.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("偏离阈值必须大于 0 且小于 1")
    ma = close.rolling(window, min_periods=window).mean()
    frame = pd.DataFrame({"close": close, "ma": ma})
    frame["buy_line"] = ma * (1 - threshold)
    frame["sell_line"] = ma * (1 + threshold)
    frame["signal"] = np.select(
        [close < frame["buy_line"], close > frame["sell_line"]],
        [1, -1],
        default=0,
    )
    return frame


@dataclass(frozen=True)
class MABand(BaseStrategy):
    window: int = 30
    threshold: float = 0.05
    weights: Mapping[str, float] | None = None
    name = "ma_band"

    def __post_init__(self):
        ma_band_signals(pd.Series(dtype=float), self.window, self.threshold)

    def initial_targets(self, pool):
        allocation(pool, self.weights)  # 即使没有触发信号也校验配置
        return None

    def on_close(self, context):
        budgets = allocation(context.pool, self.weights)
        targets = {}
        for ticker in context.pool.tickers:
            if pd.isna(context.history[ticker].iloc[-1]):
                continue
            valid = context.history[ticker].dropna().iloc[-self.window :]
            if len(valid) < self.window:
                continue
            price, ma = valid.iloc[-1], valid.mean()
            held = context.quantities[ticker] > 0
            if not held and budgets[ticker] > 0 and price < ma * (1 - self.threshold):
                targets[ticker] = budgets[ticker]
            elif held and price > ma * (1 + self.threshold):
                targets[ticker] = 0.0
        return targets or None

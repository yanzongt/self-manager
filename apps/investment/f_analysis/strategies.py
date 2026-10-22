"""策略产生目标权重或定时投入计划，不直接修改账户或计算成交数量。"""

from dataclasses import dataclass, field
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
    if frequency == "weekly":
        return tuple(date.isocalendar()[:2])
    if frequency == "monthly":
        return date.year, date.month
    if frequency == "quarterly":
        return date.year, (date.month - 1) // 3
    if frequency == "semiannual":
        return date.year, (date.month - 1) // 6
    if frequency == "annual":
        return date.year
    return date


DCA_FREQUENCIES = ("weekly", "monthly", "quarterly", "annual", "each_observation")


@dataclass(frozen=True)
class DollarCostAveraging(BaseStrategy):
    """首日投资初始资金；后续周期追加金额，仅买入新增资金对应份额。"""

    amount: float = 1000.0
    frequency: str = "monthly"
    weights: Mapping[str, float] | None = None
    name = "dca"

    def __post_init__(self):
        if isinstance(self.amount, bool) or not np.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("每期定投金额必须为有限正数")
        if self.frequency not in DCA_FREQUENCIES:
            raise ValueError("无效定投频率")

    def initial_targets(self, pool):
        allocation(pool, self.weights)
        return None

    def scheduled_investment(self, date, previous_date, pool, initial_cash):
        if previous_date is None:
            deposit, budget = 0.0, initial_cash
        elif _period_key(date, self.frequency) != _period_key(previous_date, self.frequency):
            deposit, budget = self.amount, self.amount
        else:
            return 0.0, {}
        return deposit, {t: budget * w for t, w in allocation(pool, self.weights).items() if w > 0}


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


def ma_band_signals(close, window=30, threshold=0.05, *, buy_threshold=None, sell_threshold=None,
                    buy_first_only=False, sell_first_only=False):
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("MA 窗口必须为正整数")
    buy = threshold if buy_threshold is None else buy_threshold
    sell = threshold if sell_threshold is None else sell_threshold
    for value in (buy, sell):
        if isinstance(value, bool) or not np.isfinite(value) or not 0 < value < 1:
            raise ValueError("买入和卖出偏离比例必须大于 0 且小于 1")
    ma = close.rolling(window, min_periods=window).mean()
    frame = pd.DataFrame({"close": close, "ma": ma})
    frame["buy_line"] = ma * (1 - buy)
    frame["sell_line"] = ma * (1 + sell)
    buying = close < frame["buy_line"]
    selling = close > frame["sell_line"]
    frame["signal"] = np.select(
        [buying & ~buying.shift(1, fill_value=False) if buy_first_only else buying,
         selling & ~selling.shift(1, fill_value=False) if sell_first_only else selling],
        [1, -1],
        default=0,
    )
    return frame


@dataclass(frozen=True)
class MABand(BaseStrategy):
    window: int = 30
    threshold: float = 0.05
    weights: Mapping[str, float] | None = None
    buy_threshold: float | None = None
    sell_threshold: float | None = None
    trade_mode: str = "full_position"
    buy_amount: float = 1000.0
    sell_fraction: float = 0.25
    funding_mode: str = "cash"
    buy_first_only: bool = False
    sell_first_only: bool = False
    buy_budget_mode: str = "fixed"
    extra_amount: float = 1000.0
    name = "ma_band"

    def __post_init__(self):
        ma_band_signals(pd.Series(dtype=float), self.window, self.threshold,
                        buy_threshold=self.buy_threshold, sell_threshold=self.sell_threshold)
        if self.trade_mode not in ("full_position", "independent"):
            raise ValueError("无效均线交易模式")
        if self.funding_mode not in ("cash", "auto_contribute"):
            raise ValueError("无效均线资金来源")
        if self.funding_mode == "auto_contribute" and self.trade_mode != "independent":
            raise ValueError("自动追加资金仅适用于均线独立买卖模式")
        if type(self.buy_first_only) is not bool or type(self.sell_first_only) is not bool:
            raise ValueError("买卖首次触发选项必须为布尔值")
        if self.buy_budget_mode not in ("fixed", "cash_plus_extra"):
            raise ValueError("无效均线买入预算方式")
        if self.buy_budget_mode == "cash_plus_extra" and self.trade_mode != "independent":
            raise ValueError("全现金加额外投入仅适用于独立买卖模式")
        if isinstance(self.extra_amount, bool) or not np.isfinite(self.extra_amount) or self.extra_amount < 0:
            raise ValueError("均线额外投入金额必须为非负有限数")
        if isinstance(self.buy_amount, bool) or not np.isfinite(self.buy_amount) or self.buy_amount <= 0:
            raise ValueError("均线每次买入总预算必须为有限正数")
        if isinstance(self.sell_fraction, bool) or not np.isfinite(self.sell_fraction) or not 0 < self.sell_fraction <= 1:
            raise ValueError("均线每次卖出比例必须大于 0 且不超过 1")

    @property
    def buy_deviation(self):
        return self.threshold if self.buy_threshold is None else self.buy_threshold

    @property
    def sell_deviation(self):
        return self.threshold if self.sell_threshold is None else self.sell_threshold

    def initial_targets(self, pool):
        allocation(pool, self.weights)  # 即使没有触发信号也校验配置
        return None

    def triggers(self, context, ticker):
        if pd.isna(context.history[ticker].iloc[-1]):
            return False, False
        recent = context.history[ticker].dropna().iloc[-self.window - 1:]
        if len(recent) < self.window:
            return False, False
        price, ma = recent.iloc[-1], recent.iloc[-self.window:].mean()
        buy = price < ma * (1 - self.buy_deviation)
        sell = price > ma * (1 + self.sell_deviation)
        if len(recent) > self.window:
            previous, previous_ma = recent.iloc[-2], recent.iloc[:-1].mean()
            if self.buy_first_only:
                buy = buy and not previous < previous_ma * (1 - self.buy_deviation)
            if self.sell_first_only:
                sell = sell and not previous > previous_ma * (1 + self.sell_deviation)
        return bool(buy), bool(sell)

    def on_close(self, context):
        if self.trade_mode == "independent":
            return None
        budgets = allocation(context.pool, self.weights)
        targets = {}
        for ticker in context.pool.tickers:
            buy, sell = self.triggers(context, ticker)
            held = context.quantities[ticker] > 0
            if not held and budgets[ticker] > 0 and buy:
                targets[ticker] = budgets[ticker]
            elif held and sell:
                targets[ticker] = 0.0
        return targets or None

    def on_close_orders(self, context):
        """独立买卖：买入不检查是否已持仓，卖出只受实际可卖持仓限制。"""
        buys, sells = {}, {}
        if self.trade_mode != "independent":
            return buys, sells
        weights = allocation(context.pool, self.weights)
        for ticker in context.pool.tickers:
            buy, sell = self.triggers(context, ticker)
            if weights[ticker] > 0 and buy:
                buys[ticker] = weights[ticker] if self.buy_budget_mode == "cash_plus_extra" else self.buy_amount * weights[ticker]
            if context.quantities[ticker] > 0 and sell:
                sells[ticker] = self.sell_fraction
        return buys, sells


@dataclass
class CrossSectionalMomentum(BaseStrategy):
    """收盘排名，次个有效收盘成交；不足 N 个合格标的时空缺份额留现金。"""

    lookback: int = 126
    rebalance_interval: int = 21
    top_n: int = 1
    name = "cross_sectional_momentum"
    _last_signal: int | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        for value in (self.lookback, self.rebalance_interval, self.top_n):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("动量回看长度、调仓间隔及持股数量必须为正整数")

    def initial_targets(self, pool):
        if self.top_n > len(pool.tickers):
            raise ValueError("动量持股数量不能超过股票池大小")
        self._last_signal = None
        return None

    def on_close(self, context):
        position = len(context.history) - 1
        if position < self.lookback or (
            self._last_signal is not None
            and position - self._last_signal < self.rebalance_interval
        ):
            return None
        window = context.history.iloc[-self.lookback - 1:]
        eligible = window.columns[window.notna().all()]
        returns = window.iloc[-1][eligible] / window.iloc[0][eligible] - 1
        # 排名相同时按代码排序，结果不依赖输入股票顺序。
        ranked = sorted(returns.index, key=lambda t: (-returns[t], t))[:self.top_n]
        self._last_signal = position
        return {t: 1 / self.top_n if t in ranked else 0.0 for t in context.pool.tickers}

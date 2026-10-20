"""旧的双资产研究脚本使用同一账户引擎，保留其采样和展示接口。"""

from . import (
    BacktestConfig,
    BacktestEngine,
    BuyAndHold,
    FixedWeightRebalance,
    StockPool,
)


def pair_backtest(prices, weight=0.5, *, rebalance=False, fee_rate=0.0):
    if len(prices.columns) != 2:
        raise ValueError("此兼容接口需要恰好两只资产")
    pool = StockPool.from_tickers(prices.columns)
    weights = dict(zip(pool.tickers, [weight, 1 - weight]))
    strategy = (
        FixedWeightRebalance(weights, "each_observation")
        if rebalance
        else BuyAndHold(weights)
    )
    return BacktestEngine(
        pool, BacktestConfig(initial_cash=1.0, fee_rate=fee_rate)
    ).run(prices, strategy)

"""供所有策略共用的绩效与行情分析。"""

import numpy as np
import pandas as pd


def equity_metrics(history, initial_cash):
    history = history.copy()
    previous = history["equity"].shift(1, fill_value=initial_cash)
    history["daily_pnl"] = history["equity"] - previous
    history["daily_return"] = history["equity"] / previous - 1
    history["cumulative_pnl"] = history["equity"] - initial_cash
    history["total_return"] = history["equity"] / initial_cash - 1
    history["drawdown"] = (
        history["equity"] / history["equity"].cummax().clip(lower=initial_cash) - 1
    )
    return history


def summarize(history, trades, config, strategy, pending_count):
    first, last = history.index[0], history.index[-1]
    final = history.iloc[-1]
    closed = trades.loc[trades["status"] == "closed"]
    years = (last - first).total_seconds() / (365.25 * 86400)
    with np.errstate(over="ignore", invalid="ignore"):
        cagr = (
            np.expm1(np.log(final["equity"] / config.initial_cash) / years)
            if years > 0
            else np.nan
        )
    return {
        "strategy": strategy,
        "start": first.date().isoformat(),
        "end": last.date().isoformat(),
        "trading_days": len(history),
        "initial_cash": config.initial_cash,
        "final_equity": float(final["equity"]),
        "total_pnl": float(final["equity"] - config.initial_cash),
        "total_return": float(final["total_return"]),
        "cagr": float(cagr) if np.isfinite(cagr) else None,
        "max_drawdown": float(history["drawdown"].min()),
        "realized_pnl": float(final["realized_pnl"]),
        "unrealized_pnl": float(final["unrealized_pnl"]),
        "final_cash": float(final["cash"]),
        "final_market_value": float(final["market_value"]),
        "total_fees": float(final["fees"]),
        "closed_trades": len(closed),
        "open_trades": int((trades["status"] == "open").sum()),
        "win_rate": float((closed["pnl"] > 0).mean()) if len(closed) else None,
        "best_trade_pnl": float(closed["pnl"].max()) if len(closed) else None,
        "worst_trade_pnl": float(closed["pnl"].min()) if len(closed) else None,
        "pending_orders": pending_count,
    }


def period_performance(history, initial_cash, rule):
    equity = history["equity"].resample(rule).last().dropna()
    previous = equity.shift(1, fill_value=initial_cash)
    return pd.DataFrame(
        {
            "ending_equity": equity,
            "pnl": equity - previous,
            "return": equity / previous - 1,
            "cumulative_pnl": equity - initial_cash,
        }
    )


def correlation_analysis(prices, rule=None):
    """保留各标的独立历史，相关矩阵按列两两匹配有效收益。"""
    sampled = prices if rule is None else prices.resample(rule).last()
    returns = sampled.pct_change(fill_method=None)
    return returns, returns.corr()

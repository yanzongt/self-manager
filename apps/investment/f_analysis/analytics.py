"""供所有策略共用的绩效与行情分析。"""

import numpy as np
import pandas as pd


def equity_metrics(history, initial_cash):
    history = history.copy()
    previous = history["equity"].shift(1, fill_value=initial_cash)
    flow = history.get("contribution", pd.Series(0.0, index=history.index))
    history["daily_pnl"] = history["equity"] - previous - flow
    history["daily_return"] = (history["equity"] - flow) / previous - 1
    if "pre_contribution_equity" in history:
        # 入金发生在收盘成交前：先计算旧资金截至入金前的表现，再计算入金后成交的费用。
        # 不能将新资金买入产生的手续费全部除以旧本金，否则大额补款会产生低于 -100% 的假收益。
        before_flow = history["pre_contribution_equity"]
        funded = flow.ne(0) & before_flow.notna()
        history.loc[funded, "daily_return"] = (
            before_flow[funded] / previous[funded]
            * history.loc[funded, "equity"] / (before_flow[funded] + flow[funded]) - 1
        )
    history["cumulative_pnl"] = history["equity"] - initial_cash - flow.cumsum()
    if flow.ne(0).any():
        nav = (1 + history["daily_return"]).cumprod()
        history["total_return"] = nav - 1
        history["drawdown"] = nav / nav.cummax().clip(lower=1.0) - 1
    else:
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
            np.expm1(np.log1p(final["total_return"]) / years)
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
        "total_contributed": float(final.get("total_contributed", config.initial_cash)),
        "additional_contributions": float(final.get("total_contributed", config.initial_cash) - config.initial_cash),
        "total_pnl": float(final["cumulative_pnl"]),
        "profit_on_contributed": float(final["cumulative_pnl"] / final.get("total_contributed", config.initial_cash)),
        "return_method": "time_weighted" if strategy == "dca" or history.get("contribution", pd.Series(dtype=float)).ne(0).any() else "initial_capital",
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
    if "contribution" in history and history["contribution"].ne(0).any():
        nav = (1 + history["total_return"]).resample(rule).last().dropna()
        flow = history["contribution"].resample(rule).sum().reindex(equity.index)
        return pd.DataFrame({
            "ending_equity": equity, "contribution": flow,
            "pnl": equity - previous - flow,
            "return": nav / nav.shift(1, fill_value=1.0) - 1,
            "cumulative_pnl": history["cumulative_pnl"].resample(rule).last().reindex(equity.index),
        })
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

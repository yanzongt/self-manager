"""单股票策略回测：MA 偏离策略与首日买入持有策略。"""

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f_analysis import BacktestConfig, BacktestEngine, BuyAndHold, MABand, StockPool
from f_analysis.research import add_research_arguments, arguments_config, evaluate_robustness
from f_analysis.reporting import save_research
from f_analysis.analytics import period_performance
from f_analysis.strategies import ma_band_signals

from ._runtime import create_parser, prepare_run, save_plot
from .market_data import get_prices

TICKER = "600036.SS"
PERIOD = "5y"
INITIAL_CASH = 100_000.0
MA_WINDOW = 30
THRESHOLD = 0.05
FEE_RATE = 0.0
STRATEGIES = ("ma_band", "buy_hold")


def backtest(
    close,
    *,
    initial_cash=INITIAL_CASH,
    window=MA_WINDOW,
    threshold=THRESHOLD,
    fee_rate=FEE_RATE,
    strategy="ma_band",
    buy_threshold=None,
    sell_threshold=None,
    return_result=False,
    trade_mode="full_position",
    buy_amount=1000,
    sell_fraction=0.25,
    funding_mode="cash",
    buy_first_only=False,
    sell_first_only=False,
    buy_budget_mode="fixed",
    extra_amount=1000,
):
    """原单股票 API 的兼容入口；成交和账本统一由多资产引擎处理。"""
    if strategy not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy}")
    close = close.dropna().astype(float)
    if strategy == "ma_band":
        selected = MABand(window, threshold, buy_threshold=buy_threshold, sell_threshold=sell_threshold,
                          trade_mode=trade_mode, buy_amount=buy_amount, sell_fraction=sell_fraction, funding_mode=funding_mode,
                          buy_first_only=buy_first_only, sell_first_only=sell_first_only,
                          buy_budget_mode=buy_budget_mode, extra_amount=extra_amount)
        if len(close) < window:
            raise ValueError(
                f"行情只有 {len(close)} 个有效价格，不足 MA{window} 所需数据"
            )
    else:
        selected = BuyAndHold()
    pool = StockPool.from_tickers(["asset"])
    # StockPool 统一代码为大写。
    ticker = pool.tickers[0]
    prices = close.to_frame(ticker)
    engine = BacktestEngine(pool, BacktestConfig(initial_cash, fee_rate))
    result = engine.run(prices, selected)
    benchmark = result if strategy == "buy_hold" else engine.run(prices, BuyAndHold())
    diagnostics = (
        ma_band_signals(close, window, threshold, buy_threshold=buy_threshold, sell_threshold=sell_threshold,
                        buy_first_only=buy_first_only, sell_first_only=sell_first_only)
        if strategy == "ma_band"
        else pd.DataFrame({"close": close, "signal": 0})
    )
    history = result.history.join(diagnostics)
    history["quantity"] = result.positions.set_index("date")["quantity"]
    history["executed_action"] = (
        result.fills.groupby("date")["side"]
        .last()
        .reindex(history.index)
        .fillna("hold")
    )
    history["buy_hold_equity"] = benchmark.history["equity"]
    history["buy_hold_return"] = benchmark.history["total_return"]
    summary = dict(result.summary)
    summary.pop("pool", None)
    summary.pop("final_quantities", None)
    pending = result.orders.loc[result.orders["status"] == "pending"]
    summary.update(
        {
            "final_quantity": float(history["quantity"].iloc[-1]),
            "buy_hold_final_equity": benchmark.summary["final_equity"],
            "buy_hold_return": benchmark.summary["total_return"],
            "pending_action": (
                "buy" if pending.iloc[-1]["order_type"] == "signal_buy_budget" or
                (pd.notna(pending.iloc[-1]["target_weight"]) and pending.iloc[-1]["target_weight"] > 0) else "sell"
            )
            if len(pending)
            else "none",
        }
    )
    values = (history, result.trades.drop(columns="ticker"), summary)
    return (*values, result) if return_result else values


def plot_result(results, ticker, output_dir, show):
    fig, axes = plt.subplots(3, 1, figsize=(13, 12), sharex=True)
    first_history = next(iter(results.values()))[0]
    axes[0].plot(first_history.index, first_history["close"], label="Adjusted Close")
    for strategy, (history, _, _) in results.items():
        if strategy == "ma_band":
            for column in ["ma", "buy_line", "sell_line"]:
                axes[0].plot(history.index, history[column], label=column)
        for action, marker in [("buy", "^"), ("sell", "v")]:
            points = history.loc[history["executed_action"] == action]
            if not points.empty:
                axes[0].scatter(
                    points.index,
                    points["close"],
                    marker=marker,
                    label=f"{strategy}: {action}",
                    zorder=3,
                )
        axes[1].plot(history.index, history["total_return"] * 100, label=strategy)
        axes[2].plot(history.index, history["drawdown"] * 100, label=strategy)
    axes[0].set_title(f"{ticker}: Strategy Comparison")
    axes[1].set_ylabel("Cumulative Return (%)")
    axes[2].set_ylabel("Drawdown (%)")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend()
    fig.tight_layout()
    save_plot(output_dir, "backtest.png", show)


def save_result(output_dir, history, trades, summary, initial_cash):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    history.to_csv(output_dir / "daily_history.csv")
    trades.to_csv(output_dir / "trades.csv", index=False)
    period_performance(history, initial_cash, "ME").to_csv(
        output_dir / "monthly_returns.csv"
    )
    period_performance(history, initial_cash, "YE").to_csv(
        output_dir / "yearly_returns.csv"
    )


def print_summary(summary):
    print(f"\n=== {summary['strategy']} ===")
    print(f"区间: {summary['start']} ~ {summary['end']}")
    print(
        f"初始资金: {summary['initial_cash']:,.2f} | 最终资产: {summary['final_equity']:,.2f}"
    )
    print(
        f"累计盈亏: {summary['total_pnl']:,.2f} | 累计收益: {summary['total_return']:.2%}"
    )
    cagr = f"{summary['cagr']:.2%}" if summary["cagr"] is not None else "无有效年化区间"
    print(f"年化收益: {cagr} | 累计手续费: {summary['total_fees']:,.2f}")
    print(f"最大回撤: {summary['max_drawdown']:.2%}")
    print(
        f"已实现盈亏: {summary['realized_pnl']:,.2f} | 浮动盈亏: {summary['unrealized_pnl']:,.2f}"
    )
    win_rate = (
        f"{summary['win_rate']:.2%}"
        if summary["win_rate"] is not None
        else "无已平仓交易"
    )
    print(
        f"已平仓: {summary['closed_trades']} 笔 | 未平仓: {summary['open_trades']} 笔 | 胜率: {win_rate}"
    )
    print(f"期末待执行信号: {summary['pending_action']}（未计入成交）")


def main():
    description = "单股票策略回测：MA 偏离与首日买入持有，可并排比较"
    parser = create_parser(description)
    parser.add_argument(
        "--strategy",
        choices=["all", *STRATEGIES],
        default="all",
        help="默认 all 同时运行两种策略；也可单独选择",
    )
    parser.add_argument("--ticker", default=TICKER, help="Yahoo 股票代码")
    parser.add_argument("--period", default=PERIOD, help="分析范围，如 3y、5y、max")
    parser.add_argument(
        "--initial-cash", type=float, default=INITIAL_CASH, help="初始资金"
    )
    parser.add_argument("--ma-window", type=int, default=MA_WINDOW, help="均线交易日数")
    parser.add_argument(
        "--threshold", type=float, default=THRESHOLD, help="偏离比例，0.05 表示 5%%"
    )
    parser.add_argument(
        "--fee-rate", type=float, default=FEE_RATE, help="买卖各自的单边费率"
    )
    add_research_arguments(parser, momentum=False)
    args = parser.parse_args()
    try:
        research = arguments_config(args)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    args.ticker = args.ticker.strip().upper()
    if not args.ticker:
        parser.error("股票代码不能为空")
    if not np.isfinite(args.initial_cash) or args.initial_cash <= 0:
        parser.error("初始资金必须为有限正数")
    if args.strategy != "buy_hold" and (
        args.ma_window < 1
        or not np.isfinite(args.threshold)
        or not 0 < args.threshold < 1
    ):
        parser.error("MA 窗口须为正整数，偏离比例须在 0 和 1 之间")
    if not np.isfinite(args.fee_rate) or not 0 <= args.fee_rate < 1:
        parser.error("费率须大于等于 0 且小于 1")
    config = {
        key: getattr(args, key)
        for key in [
            "ticker",
            "period",
            "initial_cash",
            "ma_window",
            "threshold",
            "fee_rate",
        ]
    }
    config.update(research)
    strategies = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    config.update(
        {
            "strategies": strategies,
            "force_liquidate": False,
            "execution": {
                name: "next_available_close" if name == "ma_band" else "first_close"
                for name in strategies
            },
        }
    )
    output_dir, show, data_options = prepare_run(
        "single_stock_backtest",
        description,
        config,
        args=args,
    )
    prices = get_prices([args.ticker], period=args.period, **data_options)
    results = {}
    # 一次取数，所有策略使用完全相同的行情和账户计价逻辑。
    for strategy in strategies:
        history, trades, summary, core_result = backtest(
            prices[args.ticker],
            initial_cash=args.initial_cash,
            window=args.ma_window,
            threshold=args.threshold,
            fee_rate=args.fee_rate,
            strategy=strategy,
            buy_threshold=research["buy_threshold"],
            sell_threshold=research["sell_threshold"],
            return_result=True,
            trade_mode=research["ma_trade_mode"],
            buy_amount=research["ma_buy_amount"],
            sell_fraction=research["ma_sell_fraction"],
            funding_mode=research["ma_funding_mode"],
            buy_first_only=research["ma_buy_first_only"],
            sell_first_only=research["ma_sell_first_only"],
            buy_budget_mode=research["ma_buy_budget_mode"],
            extra_amount=research["ma_extra_amount"],
        )
        pool = StockPool.from_tickers(["ASSET"])
        selected = (MABand(args.ma_window, args.threshold,
                          buy_threshold=research["buy_threshold"], sell_threshold=research["sell_threshold"],
                          trade_mode=research["ma_trade_mode"], buy_amount=research["ma_buy_amount"],
                          sell_fraction=research["ma_sell_fraction"], funding_mode=research["ma_funding_mode"],
                          buy_first_only=research["ma_buy_first_only"], sell_first_only=research["ma_sell_first_only"],
                          buy_budget_mode=research["ma_buy_budget_mode"], extra_amount=research["ma_extra_amount"])
                    if strategy == "ma_band" else BuyAndHold())
        evaluate_robustness(BacktestEngine(pool, BacktestConfig(args.initial_cash, args.fee_rate)),
                            prices[args.ticker].dropna().to_frame("ASSET"), selected, core_result, config)
        summary.update({k: v for k, v in core_result.summary.items()
                        if k.startswith(("subperiod_", "sensitivity_", "ma_"))})
        summary.update(
            {
                "ticker": args.ticker,
                "period": args.period,
                "fee_rate": args.fee_rate,
                "execution": config["execution"][strategy],
                "force_liquidate": False,
            }
        )
        if strategy == "ma_band":
            summary.update({"ma_window": args.ma_window, "threshold": args.threshold,
                            "buy_threshold": research["buy_threshold"], "sell_threshold": research["sell_threshold"]})
        results[strategy] = history, trades, summary
        save_result(output_dir / strategy, history, trades, summary, args.initial_cash)
        save_research(output_dir / strategy, core_result)
        if not core_result.contributions.empty:
            core_result.contributions.to_csv(output_dir / strategy / "contributions.csv", index=False)
        print_summary(summary)
    comparison = pd.DataFrame([value[2] for value in results.values()])
    comparison["extra_return_vs_buy_hold"] = (
        comparison["total_return"] - comparison["buy_hold_return"]
    )
    comparison.to_csv(output_dir / "comparison.csv", index=False)
    columns = [
        "strategy",
        "final_equity",
        "total_pnl",
        "total_return",
        "cagr",
        "max_drawdown",
        "total_fees",
        "extra_return_vs_buy_hold",
    ]
    print("\n=== 策略对比（相同区间、初始资金及费率） ===")
    formatters = {
        key: "{:.2%}".format
        for key in ["total_return", "cagr", "max_drawdown", "extra_return_vs_buy_hold"]
    }
    print(comparison[columns].to_string(index=False, formatters=formatters))
    print("收益差 extra_return_vs_buy_hold 为累计收益率之差（百分点）。")
    plot_result(results, args.ticker, output_dir, show)


if __name__ == "__main__":
    main()

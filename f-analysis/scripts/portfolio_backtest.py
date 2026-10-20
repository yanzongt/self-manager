"""配置股票池与策略，统一运行多资产回测和行情分析。"""

import json
from pathlib import Path

import matplotlib.pyplot as plt

from f_analysis import (
    BacktestConfig,
    BacktestEngine,
    BuyAndHold,
    FixedWeightRebalance,
    MABand,
    StockPool,
)
from f_analysis.analytics import correlation_analysis
from f_analysis.reporting import compare_results, plot_comparison, save_result
from f_analysis.strategies import FREQUENCIES, allocation

from ._runtime import create_parser, prepare_run
from .market_data import get_prices

STRATEGY_NAMES = ("buy_hold", "ma_band", "fixed_weight")


def main():
    description = "股票池 + 策略：多资产统一回测与绩效比较"
    parser = create_parser(description)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--tickers", nargs="+", help="股票代码列表，默认招商银行和比亚迪"
    )
    source.add_argument("--pool", type=Path, help="股票池 JSON 文件：代码到名称的映射")
    parser.add_argument(
        "--weights",
        nargs="+",
        type=float,
        help="依股票池顺序的目标权重，默认等权；剩余为现金",
    )
    parser.add_argument(
        "--strategy", nargs="+", choices=["all", *STRATEGY_NAMES], default=["all"]
    )
    parser.add_argument("--period", default="5y")
    parser.add_argument("--initial-cash", type=float, default=100_000)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--ma-window", type=int, default=30)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--rebalance-frequency", choices=FREQUENCIES, default="monthly")
    args = parser.parse_args()
    try:
        pool = (
            StockPool(json.loads(args.pool.read_text(encoding="utf-8")))
            if args.pool
            else StockPool.from_tickers(args.tickers or ["600036.SS", "002594.SZ"])
        )
        if args.weights is not None and len(args.weights) != len(pool.tickers):
            parser.error("权重数量必须与股票数量一致")
        weights = allocation(
            pool,
            dict(zip(pool.tickers, args.weights)) if args.weights is not None else None,
        )
        config = BacktestConfig(args.initial_cash, args.fee_rate)
        if "all" in args.strategy and len(args.strategy) != 1:
            parser.error("all 不能与其他策略同时指定")
        names = (
            list(STRATEGY_NAMES)
            if args.strategy == ["all"]
            else list(dict.fromkeys(args.strategy))
        )
        strategies = {}
        for name in names:
            if name == "buy_hold":
                strategies[name] = BuyAndHold(weights)
            elif name == "ma_band":
                strategies[name] = MABand(args.ma_window, args.threshold, weights)
            else:
                strategies[name] = FixedWeightRebalance(
                    weights, args.rebalance_frequency
                )
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        parser.error(str(exc))
    run_config = {
        "pool": dict(pool.stocks),
        "weights": weights,
        "period": args.period,
        "strategies": names,
        "initial_cash": args.initial_cash,
        "fee_rate": args.fee_rate,
        "ma_window": args.ma_window,
        "threshold": args.threshold,
        "rebalance_frequency": args.rebalance_frequency,
        "execution": {
            "buy_hold": "first_available_close",
            "ma_band": "next_available_close",
            "fixed_weight": "first_close_of_calendar_period",
        },
        "force_liquidate": False,
    }
    output_dir, show, data_options = prepare_run(
        "portfolio_backtest", description, run_config, args=args
    )
    prices = get_prices(pool.tickers, period=args.period, **data_options)
    engine = BacktestEngine(pool, config)
    results = {}
    for name, strategy in strategies.items():
        result = engine.run(prices, strategy)
        result.summary.update(
            {"pool": dict(pool.stocks), "weights": weights, "fee_rate": args.fee_rate}
        )
        results[name] = result
        save_result(output_dir / name, result)
    comparison = compare_results(results)
    comparison.to_csv(output_dir / "comparison.csv", index=False)
    columns = [
        "strategy",
        "final_equity",
        "total_pnl",
        "total_return",
        "cagr",
        "max_drawdown",
        "total_fees",
        "pending_orders",
    ]
    print(
        comparison[columns].to_string(
            index=False,
            formatters={
                key: "{:.2%}".format for key in ["total_return", "cagr", "max_drawdown"]
            },
        )
    )
    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir()
    _, daily = correlation_analysis(prices)
    _, monthly = correlation_analysis(prices, "ME")
    daily.to_csv(analysis_dir / "daily_correlation.csv")
    monthly.to_csv(analysis_dir / "monthly_correlation.csv")
    fig = plot_comparison(results, output_dir / "comparison.png")
    if show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()

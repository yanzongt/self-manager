import pandas as pd

from f_analysis.adapters import pair_backtest

from ._runtime import prepare_run
from .market_data import get_prices

TICKERS = ["159516.SZ", "560020.SS"]
PERIOD = "3y"


def main():
    output_dir, _, data_options = prepare_run(
        "rebalance_comparison",
        "50/50 买入持有与每月再平衡对比",
        {"tickers": TICKERS, "period": PERIOD},
    )
    # 自动复权：包含分红、拆股等影响
    prices = get_prices(TICKERS, period=PERIOD, **data_options).dropna()

    # 统一从共同起始日开始
    prices = prices.dropna()

    # 月末价格
    monthly = prices.resample("ME").last()

    # 月收益
    ret = monthly.pct_change().dropna()

    print("月收益相关系数：")
    print(ret.corr())
    print()

    # -------------------------
    # 1. 买入后不再平衡
    # -------------------------

    hold_final = pair_backtest(monthly).summary["final_equity"]
    hold_return = hold_final - 1
    portfolio = pair_backtest(monthly, rebalance=True).summary["final_equity"]
    rebalance_return = portfolio - 1

    # -------------------------
    # 结果
    # -------------------------

    print(f"买入持有最终资产: {hold_final:.4f}")
    print(f"买入持有累计收益: {hold_return:.2%}")

    print()

    print(f"每月再平衡最终资产: {portfolio:.4f}")
    print(f"每月再平衡累计收益: {rebalance_return:.2%}")

    print()

    extra = rebalance_return - hold_return

    print(f"再平衡超额收益: {extra:.2%}")

    # -------------------------
    # 额外指标
    # -------------------------

    opposite = (ret[TICKERS[0]] * ret[TICKERS[1]] < 0).mean()

    relative = ret[TICKERS[0]] - ret[TICKERS[1]]

    reversal = (relative * relative.shift(1) < 0).dropna().mean()

    print()
    print(f"反向涨跌月份比例: {opposite:.2%}")
    print(f"强弱反转月份比例: {reversal:.2%}")

    ret.to_csv(output_dir / "monthly_returns.csv")
    pd.DataFrame(
        [
            {
                "strategy": "buy_hold",
                "final_value": hold_final,
                "total_return": hold_return,
            },
            {
                "strategy": "monthly_rebalance",
                "final_value": portfolio,
                "total_return": rebalance_return,
            },
        ]
    ).to_csv(output_dir / "comparison_results.csv", index=False)


if __name__ == "__main__":
    main()

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f_analysis.adapters import pair_backtest

from ._runtime import prepare_run, save_plot
from .market_data import get_prices

# ============================================================
# 配置
# ============================================================

# 半导体设备 vs 红利
TICKERS = ["159516.SZ", "560020.SS"]
# 信息技术 vs 红利低波
# TICKERS = ["512330.SS", "512890.SS"]
# 半导体设备 vs 红利低波
# TICKERS = ["159516.SZ", "512890.SS"]
# 半导体设备 vs 招商银行
# TICKERS = ["159516.SZ", "600036.SS"]
# 半导体设备 vs 港股通汽车
# TICKERS = ["159516.SZ", "159210.SZ"]


# 尽量覆盖全部历史；如果只想最近3年改成 "3y"
# PERIOD = "max"
PERIOD = "max"

# 单边交易成本（本次忽略，设为 0）
TRANSACTION_COST = 0.0

# 权重扫描范围
WEIGHTS = np.arange(0.2, 0.81, 0.05)

# 滚动回测窗口，单位：月
ROLLING_MONTHS = 36


# ============================================================
# 数据下载
# ============================================================


def download_prices(tickers, period="max", **data_options):
    # 保留 NaN，后续按月对齐，各标的共享独立缓存。
    prices = get_prices(tickers, period=period, **data_options)

    valid = prices.dropna()

    if valid.empty:
        raise RuntimeError("没有下载到有效行情数据")

    print("\n=== 数据范围 ===")
    print(f"共同起始: {valid.index[0].date()}")
    print(f"共同结束: {valid.index[-1].date()}")
    print(f"共同交易日: {len(valid)}")

    return prices


# ============================================================
# 基础统计
# ============================================================


def monthly_data(prices):
    monthly = prices.resample("ME").last().dropna()
    returns = monthly.pct_change().dropna()

    return monthly, returns


def print_correlation_stats(monthly_returns):
    a, b = monthly_returns.columns

    corr = monthly_returns[a].corr(monthly_returns[b])

    opposite = (monthly_returns[a] * monthly_returns[b] < 0).mean()

    relative = monthly_returns[a] - monthly_returns[b]

    reversal = (relative * relative.shift(1) < 0).dropna().mean()

    print("\n=== 轮动特征 ===")
    print(f"月收益相关系数:     {corr:.4f}")
    print(f"反向涨跌月份比例:   {opposite:.2%}")
    print(f"强弱反转月份比例:   {reversal:.2%}")

    return {
        "correlation": corr,
        "opposite_ratio": opposite,
        "reversal_ratio": reversal,
    }


# ============================================================
# Buy & Hold
# ============================================================


def backtest_buy_hold(monthly_prices, weight_a):
    """
    初始按照 weight_a / (1-weight_a) 买入，
    之后完全不再平衡。
    """

    return pair_backtest(monthly_prices, weight_a).summary["final_equity"]


def annualized_return(final_value, months):
    """
    把累计净值换算成年化收益（CAGR）。

    参数 months 是收益期数（= 月度价格点数 - 1）。
    """

    years = months / 12

    if years <= 0:
        return np.nan

    return final_value ** (1 / years) - 1


# ============================================================
# 再平衡回测
# ============================================================


def backtest_rebalance(
    prices,
    weight_a=0.5,
    frequency="monthly",
    transaction_cost=0.0,
):
    """
    frequency:
        monthly
        quarterly
        semiannual
        annual
    """

    freq_map = {"monthly": "ME", "quarterly": "QE", "semiannual": "2QE", "annual": "YE"}
    sampled = prices.resample(freq_map[frequency]).last().dropna()
    if len(sampled) < 2:
        return np.nan, None
    result = pair_backtest(sampled, weight_a, rebalance=True, fee_rate=transaction_cost)
    curve = result.history.rename(columns={"equity": "value"}).iloc[1:]
    return result.summary["final_equity"], curve


# ============================================================
# 比较不同频率
# ============================================================


def compare_frequencies(prices, weight=0.5):
    monthly_prices, _ = monthly_data(prices)

    # 收益期数 = 月度价格点数 - 1，与 etf_pair_scan 口径一致
    months = len(monthly_prices) - 1

    bh = backtest_buy_hold(
        monthly_prices,
        weight,
    )

    bh_cagr = annualized_return(
        bh,
        months,
    )

    results = []

    for frequency in [
        "monthly",
        "quarterly",
        "semiannual",
        "annual",
    ]:
        final_value, curve = backtest_rebalance(
            prices,
            weight_a=weight,
            frequency=frequency,
            transaction_cost=TRANSACTION_COST,
        )

        cagr = annualized_return(
            final_value,
            months,
        )

        results.append(
            {
                "strategy": frequency,
                "final_value": final_value,
                "cagr": cagr,
                "extra_vs_hold": cagr - bh_cagr,
                "total_turnover": (
                    curve["turnover"].sum() if curve is not None else np.nan
                ),
            }
        )

    results.insert(
        0,
        {
            "strategy": "buy_hold",
            "final_value": bh,
            "cagr": bh_cagr,
            "extra_vs_hold": 0,
            "total_turnover": 0,
        },
    )

    df = pd.DataFrame(results)

    print("\n=== 不同再平衡频率 ===")
    print(
        df.to_string(
            index=False,
            formatters={
                "cagr": "{:.2%}".format,
                "extra_vs_hold": "{:.2%}".format,
                "total_turnover": "{:.2f}".format,
            },
        )
    )

    return df


# ============================================================
# 权重扫描
# ============================================================


def scan_weights(prices):
    monthly_prices, _ = monthly_data(prices)

    months = len(monthly_prices) - 1

    rows = []

    for w in WEIGHTS:
        bh = backtest_buy_hold(
            monthly_prices,
            w,
        )

        rb, curve = backtest_rebalance(
            prices,
            weight_a=w,
            frequency="monthly",
            transaction_cost=TRANSACTION_COST,
        )

        bh_cagr = annualized_return(
            bh,
            months,
        )

        rb_cagr = annualized_return(
            rb,
            months,
        )

        rows.append(
            {
                "weight_a": w,
                "weight_b": 1 - w,
                "buy_hold": bh_cagr,
                "rebalance": rb_cagr,
                "extra": rb_cagr - bh_cagr,
            }
        )

    df = pd.DataFrame(rows)

    print("\n=== 权重扫描 ===")

    printable = df.copy()

    for col in ["weight_a", "weight_b"]:
        printable[col] = printable[col].map(lambda x: f"{x:.0%}")

    for col in ["buy_hold", "rebalance"]:
        printable[col] = printable[col].map(lambda x: f"{x:.2%}")

    printable["extra"] = printable["extra"].map(lambda x: f"{x:.2%}")

    print(printable.to_string(index=False))

    best = df.loc[df["rebalance"].idxmax()]

    print("\n历史最优月度再平衡权重:")
    print(f"{TICKERS[0]}: {best['weight_a']:.0%}, {TICKERS[1]}: {best['weight_b']:.0%}")

    print(f"年化收益: {best['rebalance']:.2%}")

    return df


# ============================================================
# 滚动3年回测
# ============================================================


def rolling_backtest(
    prices,
    months=36,
    weight=0.5,
):
    monthly = prices.resample("ME").last().dropna()

    rows = []

    for i in range(
        0,
        len(monthly) - months + 1,
    ):
        window = monthly.iloc[i : i + months]

        if len(window) < months:
            continue

        # Buy & Hold
        bh = backtest_buy_hold(
            window,
            weight,
        )

        # 同一引擎的月度再平衡（此历史分析保持无成本口径）。
        ret = window.pct_change().dropna()
        rb = pair_backtest(window, weight, rebalance=True).summary["final_equity"]

        corr = ret.iloc[:, 0].corr(ret.iloc[:, 1])

        # 窗口跨度 = len(window) - 1 个月
        win_months = len(window) - 1

        bh_cagr = annualized_return(
            bh,
            win_months,
        )

        rb_cagr = annualized_return(
            rb,
            win_months,
        )

        rows.append(
            {
                "start": window.index[0],
                "end": window.index[-1],
                "buy_hold": bh_cagr,
                "rebalance": rb_cagr,
                "extra": rb_cagr - bh_cagr,
                "correlation": corr,
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        print("\n历史长度不足以进行滚动3年回测")
        return df

    print("\n=== 滚动3年回测统计 ===")

    print(f"窗口数量: {len(df)}")

    print(f"再平衡胜率: {(df['extra'] > 0).mean():.2%}")

    print(f"平均超额收益: {df['extra'].mean():.2%}")

    print(f"超额收益中位数: {df['extra'].median():.2%}")

    print(f"最差超额收益: {df['extra'].min():.2%}")

    print(f"最好超额收益: {df['extra'].max():.2%}")

    return df


# ============================================================
# 最近3年净值曲线
# ============================================================


def plot_recent_3y(prices, output_dir, show=True):
    cutoff = prices.index[-1] - pd.Timedelta(days=1095)
    recent = prices.loc[prices.index >= cutoff]

    monthly = recent.resample("ME").last().dropna()

    bh_curve = pair_backtest(monthly).history["equity"]
    rb_curve = pair_backtest(monthly, rebalance=True).history["equity"]

    plt.figure(figsize=(12, 6))

    plt.plot(
        bh_curve.index,
        bh_curve,
        label="Buy & Hold 50/50",
    )

    plt.plot(
        rb_curve.index,
        rb_curve,
        label="Monthly Rebalance 50/50",
    )

    plt.title(f"{TICKERS[0]} + {TICKERS[1]}")

    plt.ylabel("Portfolio Value")
    plt.legend()
    plt.grid()

    save_plot(output_dir, "recent_3y.png", show)


# ============================================================
# 权重收益曲线
# ============================================================


def plot_weight_scan(df, output_dir, show=True):
    plt.figure(figsize=(10, 6))

    plt.plot(
        df["weight_a"],
        df["buy_hold"],
        marker="o",
        label="Buy & Hold",
    )

    plt.plot(
        df["weight_a"],
        df["rebalance"],
        marker="o",
        label="Monthly Rebalance",
    )

    plt.xlabel(f"{TICKERS[0]} Weight")

    plt.ylabel("Annualized Return")

    plt.title("Weight Scan (Annualized)")

    plt.legend()
    plt.grid()

    save_plot(output_dir, "weight_scan.png", show)


# ============================================================
# 滚动超额收益
# ============================================================


def plot_rolling_result(df, output_dir, show=True):
    if df.empty:
        return

    plt.figure(figsize=(12, 6))

    plt.plot(
        df["end"],
        df["extra"],
    )

    plt.axhline(
        0,
        linestyle="--",
    )

    plt.title("Rolling 3-Year Rebalancing Extra Return (Annualized)")

    plt.ylabel("Annualized Extra Return")

    plt.grid()

    save_plot(output_dir, "rolling_extra_return.png", show)


# ============================================================
# 主程序
# ============================================================


def main():
    output_dir, show, data_options = prepare_run(
        "rebalance_analysis",
        "再平衡频率、权重扫描及滚动回测",
        {
            "tickers": TICKERS,
            "period": PERIOD,
            "transaction_cost": TRANSACTION_COST,
            "weights": WEIGHTS.tolist(),
            "rolling_months": ROLLING_MONTHS,
        },
    )

    prices = download_prices(
        TICKERS,
        PERIOD,
        **data_options,
    )

    monthly, returns = monthly_data(prices)

    # -------------------------
    # 基础轮动指标
    # -------------------------

    print_correlation_stats(returns)

    # -------------------------
    # 不同频率
    # -------------------------

    frequency_df = compare_frequencies(
        prices,
        weight=0.5,
    )

    # -------------------------
    # 权重扫描
    # -------------------------

    weight_df = scan_weights(prices)

    # -------------------------
    # 滚动3年
    # -------------------------

    rolling_df = rolling_backtest(
        prices,
        months=ROLLING_MONTHS,
        weight=0.5,
    )

    # -------------------------
    # 保存CSV
    # -------------------------

    frequency_df.to_csv(
        output_dir / "frequency_results.csv",
        index=False,
    )

    weight_df.to_csv(
        output_dir / "weight_results.csv",
        index=False,
    )

    rolling_df.to_csv(
        output_dir / "rolling_results.csv",
        index=False,
    )

    # -------------------------
    # 画图
    # -------------------------

    plot_recent_3y(prices, output_dir, show)

    plot_weight_scan(weight_df, output_dir, show)

    plot_rolling_result(rolling_df, output_dir, show)


if __name__ == "__main__":
    main()

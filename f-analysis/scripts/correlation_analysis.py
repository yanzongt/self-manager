import matplotlib.pyplot as plt

from f_analysis.analytics import correlation_analysis

from ._runtime import prepare_run, save_plot
from .market_data import get_prices

TICKERS = ["002594.SZ", "600036.SS"]
PERIOD = "3y"


def download_prices(ticker1, ticker2, period="5y", **data_options):
    """
    下载两只股票的复权价格。
    Yahoo Finance:
      深圳: xxxx.SZ
      上海: xxxx.SS
    """
    close = get_prices([ticker1, ticker2], period=period, **data_options).dropna()
    return close


def analyze_correlation(prices):
    names = prices.columns

    # 日收益率
    daily_returns, _ = correlation_analysis(prices)
    daily_returns = daily_returns.dropna()

    # 月末价格 -> 月收益率
    monthly_returns, _ = correlation_analysis(prices, "ME")
    monthly_returns = monthly_returns.dropna()

    # Pearson 相关系数
    daily_corr = daily_returns[names[0]].corr(daily_returns[names[1]])

    monthly_corr = monthly_returns[names[0]].corr(monthly_returns[names[1]])

    print("=== 相关性分析 ===")
    print(f"日收益相关性: {daily_corr:.4f}")
    print(f"月收益相关性: {monthly_corr:.4f}")

    print("\n=== 日收益相关矩阵 ===")
    print(daily_returns.corr())

    print("\n=== 月收益相关矩阵 ===")
    print(monthly_returns.corr())

    return daily_returns, monthly_returns


def rolling_correlation(monthly_returns, window=12):
    """
    计算滚动相关性。
    window=12 表示过去12个月。
    """
    a = monthly_returns.columns[0]
    b = monthly_returns.columns[1]

    return monthly_returns[a].rolling(window).corr(monthly_returns[b])


def plot_result(prices, monthly_returns, output_dir, show=True):
    names = prices.columns

    # -------------------
    # 1. 归一化股价走势
    # -------------------
    normalized = prices / prices.iloc[0]

    plt.figure(figsize=(12, 5))

    for name in names:
        plt.plot(
            normalized.index,
            normalized[name],
            label=name,
        )

    plt.title("Normalized Price")
    plt.ylabel("Growth of 1 Yuan")
    plt.legend()
    plt.grid(True)
    save_plot(output_dir, "normalized_prices.png", show)

    # -------------------
    # 2. 月收益散点图
    # -------------------
    plt.figure(figsize=(7, 7))

    plt.scatter(
        monthly_returns[names[0]],
        monthly_returns[names[1]],
        alpha=0.7,
    )

    plt.xlabel(f"{names[0]} Monthly Return")
    plt.ylabel(f"{names[1]} Monthly Return")

    corr = monthly_returns[names[0]].corr(monthly_returns[names[1]])

    plt.title(f"Monthly Return Correlation = {corr:.3f}")
    plt.grid(True)
    save_plot(output_dir, "monthly_returns_scatter.png", show)

    # -------------------
    # 3. 12个月滚动相关性
    # -------------------
    rolling_corr = rolling_correlation(
        monthly_returns,
        window=12,
    )

    plt.figure(figsize=(12, 5))
    plt.plot(rolling_corr.index, rolling_corr)

    plt.axhline(0, linestyle="--")
    plt.title("12-Month Rolling Correlation")
    plt.ylabel("Correlation")
    plt.grid(True)
    save_plot(output_dir, "rolling_correlation.png", show)


def main():
    output_dir, show, data_options = prepare_run(
        "correlation_analysis",
        "双资产日/月收益相关性分析",
        {"tickers": TICKERS, "period": PERIOD, "rolling_window": 12},
    )
    prices = download_prices(*TICKERS, period=PERIOD, **data_options)
    daily_returns, monthly_returns = analyze_correlation(prices)
    daily_returns.to_csv(output_dir / "daily_returns.csv")
    monthly_returns.to_csv(output_dir / "monthly_returns.csv")
    plot_result(prices, monthly_returns, output_dir, show)


if __name__ == "__main__":
    main()

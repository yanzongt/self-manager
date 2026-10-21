import itertools

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from f_analysis.adapters import pair_backtest

from ._runtime import prepare_run, save_plot
from .market_data import get_prices


def _configure_chinese_font():
    """
    配置 matplotlib 使用可用的中文字体，避免中文显示为乱码/方框。
    """

    from matplotlib import font_manager

    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "AR PL UKai CN",
        "Droid Sans Fallback",
        "WenQuanYi Zen Hei",
        "SimHei",
    ]

    available = {f.name for f in font_manager.fontManager.ttflist}

    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            break

    # 避免负号显示为方框
    plt.rcParams["axes.unicode_minus"] = False


ETF_POOL = {
    "半导体设备ETF": "159516.SZ",
    "半导体ETF": "512480.SS",
    "信息科技ETF": "512330.SS",
    "科创50ETF": "588000.SS",
    "创业板ETF": "159915.SZ",
    "红利低波ETF": "512890.SS",
    "红利ETF": "510880.SS",
    "红利低波100ETF": "515100.SS",
    "黄金ETF": "518880.SS",
    "5年国债ETF": "511010.SS",
    "港股通汽车": "159210.SZ",
    "招商银行": "600036.SS",
    "比亚迪": "002594.SZ",
}


# 至少要求多少个月共同历史
MIN_MONTHS = 12

# 交易成本，单边（本次忽略，设为 0）
TRANSACTION_COST = 0.0


def download_prices(pool, **data_options):
    return get_prices(list(pool.values()), period="max", **data_options)


def get_pair_monthly(prices, ticker_a, ticker_b):
    """
    每一对ETF单独做数据对齐，避免上市日期不同导致全局数据被大量删除。
    """

    pair = prices[[ticker_a, ticker_b]].copy()

    # 每只ETF各自月末最后一个有效价格
    monthly = pair.resample("ME").last()

    # 只保留两者都存在的月份
    monthly = monthly.dropna()

    return monthly


def calc_max_drawdown(curve):
    running_max = curve.cummax()

    drawdown = curve / running_max - 1

    return drawdown.min()


def buy_hold_curve(monthly, weight=0.5):
    return pair_backtest(monthly, weight).history["equity"]


def rebalance_curve(monthly, weight=0.5, transaction_cost=0.0):
    return pair_backtest(
        monthly, weight, rebalance=True, fee_rate=transaction_cost
    ).history["equity"]


def annualized_return(
    final_value,
    months,
):
    years = months / 12

    if years <= 0:
        return np.nan

    return final_value ** (1 / years) - 1


def analyze_pair(
    prices,
    name_a,
    ticker_a,
    name_b,
    ticker_b,
):
    monthly = get_pair_monthly(
        prices,
        ticker_a,
        ticker_b,
    )

    if len(monthly) < MIN_MONTHS:
        return None

    returns = monthly.pct_change().dropna()

    if len(returns) < MIN_MONTHS - 1:
        return None

    a = returns.columns[0]
    b = returns.columns[1]

    # -----------------------
    # 相关性
    # -----------------------

    correlation = returns[a].corr(returns[b])

    # -----------------------
    # 同涨同跌 / 反向月份
    # -----------------------

    opposite_ratio = ((returns[a] * returns[b]) < 0).mean()

    # -----------------------
    # 相对强弱切换
    # -----------------------

    relative = returns[a] - returns[b]

    reversal_ratio = ((relative * relative.shift(1)) < 0).dropna().mean()

    # -----------------------
    # Buy & Hold
    # -----------------------

    bh_curve = buy_hold_curve(
        monthly,
        weight=0.5,
    )

    bh_final = bh_curve.iloc[-1]

    # -----------------------
    # Monthly Rebalance
    # -----------------------

    rb_curve = rebalance_curve(
        monthly,
        weight=0.5,
        transaction_cost=TRANSACTION_COST,
    )

    rb_final = rb_curve.iloc[-1]

    # -----------------------
    # 总超额
    # -----------------------

    extra = rb_final - bh_final

    months = len(monthly) - 1

    # -----------------------
    # 年化收益
    # -----------------------

    bh_cagr = annualized_return(
        bh_final,
        months,
    )

    rb_cagr = annualized_return(
        rb_final,
        months,
    )

    annualized_extra = rb_cagr - bh_cagr

    # -----------------------
    # 最大回撤
    # -----------------------

    bh_mdd = calc_max_drawdown(bh_curve)

    rb_mdd = calc_max_drawdown(rb_curve)

    return {
        "name_a": name_a,
        "name_b": name_b,
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "start": monthly.index[0].date(),
        "end": monthly.index[-1].date(),
        "months": months,
        "corr": correlation,
        "opposite_ratio": opposite_ratio,
        "reversal_ratio": reversal_ratio,
        "buy_hold_return": (bh_final - 1),
        "rebalance_return": (rb_final - 1),
        "extra_return": extra,
        "buy_hold_cagr": bh_cagr,
        "rebalance_cagr": rb_cagr,
        "annualized_extra": (annualized_extra),
        "buy_hold_mdd": bh_mdd,
        "rebalance_mdd": rb_mdd,
    }


def scan_all_pairs(prices):
    results = []

    items = list(ETF_POOL.items())

    for (
        (name_a, ticker_a),
        (name_b, ticker_b),
    ) in itertools.combinations(
        items,
        2,
    ):
        result = analyze_pair(
            prices,
            name_a,
            ticker_a,
            name_b,
            ticker_b,
        )

        if result is not None:
            results.append(result)

    df = pd.DataFrame(results)

    if df.empty:
        return df

    # 优先按年化再平衡增益排序
    df = df.sort_values(
        "annualized_extra",
        ascending=False,
    )

    return df


def print_results(df):
    if df.empty:
        print("没有足够历史数据的组合")
        return

    show = df.copy()

    show["组合"] = show["name_a"] + " + " + show["name_b"]

    columns = [
        "组合",
        "months",
        "corr",
        "opposite_ratio",
        "reversal_ratio",
        "buy_hold_cagr",
        "rebalance_cagr",
        "annualized_extra",
        "buy_hold_mdd",
        "rebalance_mdd",
    ]

    show = show[columns]

    rename = {
        "months": "月数",
        "corr": "相关性",
        "opposite_ratio": "反向月份",
        "reversal_ratio": "强弱反转",
        "buy_hold_cagr": "持有年化",
        "rebalance_cagr": "再平衡年化",
        "annualized_extra": "再平衡年化超额",
        "buy_hold_mdd": "持有最大回撤",
        "rebalance_mdd": "再平衡最大回撤",
    }

    show = show.rename(columns=rename)

    print(
        show.to_string(
            index=False,
            formatters={
                "相关性": "{:.3f}".format,
                "反向月份": "{:.1%}".format,
                "强弱反转": "{:.1%}".format,
                "持有年化": "{:.2%}".format,
                "再平衡年化": "{:.2%}".format,
                "再平衡年化超额": "{:.2%}".format,
                "持有最大回撤": "{:.2%}".format,
                "再平衡最大回撤": "{:.2%}".format,
            },
        )
    )


def plot_top_pairs(df, output_dir, show=True, top_n=15):
    if df.empty:
        return

    _configure_chinese_font()

    top = df.head(top_n).copy()

    labels = top["name_a"] + "\n+\n" + top["name_b"]

    values = top["annualized_extra"] * 100

    plt.figure(figsize=(12, 8))

    plt.barh(
        labels[::-1],
        values[::-1],
    )

    plt.xlabel("Annualized Rebalancing Extra Return (%)")

    plt.title("ETF Pair Rebalancing Ranking")

    plt.grid(
        axis="x",
        alpha=0.3,
    )

    plt.tight_layout()
    save_plot(output_dir, "top_pairs.png", show)


def main():
    output_dir, show, data_options = prepare_run(
        "etf_pair_scan",
        "资产池两两组合月度再平衡扫描",
        {
            "pool": ETF_POOL,
            "period": "max",
            "min_months": MIN_MONTHS,
            "transaction_cost": TRANSACTION_COST,
            "top_n": 15,
        },
    )
    print("Loading ETF prices...")

    prices = download_prices(ETF_POOL, **data_options)

    print("\nScanning pairs...")

    result = scan_all_pairs(prices)

    print_results(result)

    result.to_csv(
        output_dir / "etf_rotation_scan.csv",
        index=False,
    )

    print(f"\n结果已保存到 {output_dir / 'etf_rotation_scan.csv'}")

    plot_top_pairs(
        result,
        output_dir,
        show,
        top_n=15,
    )


if __name__ == "__main__":
    main()

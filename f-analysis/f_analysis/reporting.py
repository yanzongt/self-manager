"""标准回测结果的文件输出与策略对比。"""

import json

import matplotlib.pyplot as plt
import pandas as pd

from .analytics import period_performance


def save_result(output_dir, result):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    for name in ["history", "positions", "fills", "trades", "orders"]:
        frame = getattr(result, name)
        frame.to_csv(
            output_dir / ("daily_history.csv" if name == "history" else f"{name}.csv"),
            index=name == "history",
        )
    for rule, filename in [("ME", "monthly_returns.csv"), ("YE", "yearly_returns.csv")]:
        period_performance(result.history, result.summary["initial_cash"], rule).to_csv(
            output_dir / filename
        )


def compare_results(results):
    if not results:
        raise ValueError("至少需要一个策略结果")
    first = next(iter(results.values()))
    for result in results.values():
        if (
            not result.history.index.equals(first.history.index)
            or result.summary["initial_cash"] != first.summary["initial_cash"]
            or result.summary["fee_rate"] != first.summary["fee_rate"]
        ):
            raise ValueError("策略对比需要相同的行情日期、初始资金和费率")
    comparison = pd.DataFrame([result.summary for result in results.values()])
    if "buy_hold" in results:
        benchmark = results["buy_hold"].summary["total_return"]
        comparison["extra_return_vs_buy_hold"] = comparison["total_return"] - benchmark
    return comparison


def plot_comparison(results, output_path):
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for name, result in results.items():
        axes[0].plot(
            result.history.index, result.history["total_return"] * 100, label=name
        )
        axes[1].plot(result.history.index, result.history["drawdown"] * 100, label=name)
    axes[0].set_ylabel("Cumulative Return (%)")
    axes[1].set_ylabel("Drawdown (%)")
    for ax in axes:
        ax.legend()
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    return fig

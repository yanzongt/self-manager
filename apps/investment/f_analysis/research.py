"""配置构造、独立子区间回测及单因素参数扰动；全部复用同一账户引擎。"""

from dataclasses import replace

import numpy as np
import pandas as pd

from .strategies import BuyAndHold, CrossSectionalMomentum, DollarCostAveraging, DCA_FREQUENCIES, FixedWeightRebalance, MABand


def integer(value, label, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{label}必须为整数")
    try:
        converted = int(value)
        valid = float(value) == converted and minimum <= converted <= maximum
    except (ValueError, TypeError, OverflowError):
        valid = False
    if not valid:
        raise ValueError(f"{label}必须为 {minimum}～{maximum} 的整数")
    return converted


def research_config(data):
    """旧请求无新字段时保持原回测行为；0 个子区间表示不启用。"""
    count = integer(data.get("subperiod_count", 0), "子区间数量", 0, 50)
    if count == 1:
        raise ValueError("子区间数量应为 0（关闭）或 2～50")
    enabled = data.get("sensitivity_enabled", False)
    if type(enabled) is not bool:
        raise ValueError("扰动分析开关必须为布尔值")
    try:
        perturbation = float(data.get("perturbation", 0.1))
        buy = float(data.get("buy_threshold", data.get("threshold", 0.05)))
        sell = float(data.get("sell_threshold", data.get("threshold", 0.05)))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("偏离比例和扰动幅度必须为有效数字") from None
    if not np.isfinite(perturbation) or not 0 < perturbation < 1:
        raise ValueError("相对扰动幅度必须大于 0 且小于 1")
    mode = data.get("ma_trade_mode", "full_position")
    funding_mode = data.get("ma_funding_mode", "cash")
    buy_first_only = data.get("ma_buy_first_only", False)
    sell_first_only = data.get("ma_sell_first_only", False)
    budget_mode = data.get("ma_buy_budget_mode", "fixed")
    if any(isinstance(data.get(key), bool) for key in ("ma_buy_amount", "ma_sell_fraction", "ma_extra_amount")):
        raise ValueError("均线买入预算和卖出比例必须为有效数字")
    try:
        buy_amount = float(data.get("ma_buy_amount", 1000))
        sell_fraction = float(data.get("ma_sell_fraction", 0.25))
        extra_amount = float(data.get("ma_extra_amount", 1000))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("均线买入预算和卖出比例必须为有效数字") from None
    MABand(buy_threshold=buy, sell_threshold=sell, trade_mode=mode,
           buy_amount=buy_amount, sell_fraction=sell_fraction, funding_mode=funding_mode,
           buy_first_only=buy_first_only, sell_first_only=sell_first_only,
           buy_budget_mode=budget_mode, extra_amount=extra_amount)
    if isinstance(data.get("dca_amount"), bool):
        raise ValueError("每期定投金额必须为有限正数")
    try:
        dca_amount = float(data.get("dca_amount", 1000))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("每期定投金额必须为有限正数") from None
    dca_frequency = data.get("dca_frequency", "monthly")
    DollarCostAveraging(dca_amount, dca_frequency)
    return {
        "ma_trade_mode": mode,
        "ma_buy_first_only": buy_first_only,
        "ma_sell_first_only": sell_first_only,
        "ma_buy_budget_mode": budget_mode,
        "ma_extra_amount": extra_amount,
        "ma_funding_mode": funding_mode,
        "ma_buy_amount": buy_amount,
        "ma_sell_fraction": sell_fraction,
        "dca_amount": dca_amount,
        "dca_frequency": dca_frequency,
        "buy_threshold": buy,
        "sell_threshold": sell,
        "momentum_lookback": integer(data.get("momentum_lookback", 126), "动量回看长度", 1, 5000),
        "momentum_interval": integer(data.get("momentum_interval", 21), "动量调仓间隔", 1, 5000),
        "momentum_top_n": integer(data.get("momentum_top_n", 1), "动量持股数量", 1, 50),
        "subperiod_count": count,
        "sensitivity_enabled": enabled,
        "perturbation": perturbation,
    }


def make_strategy(name, config):
    weights = config.get("weights")
    if name == "dca":
        return DollarCostAveraging(config.get("dca_amount", 1000), config.get("dca_frequency", "monthly"), weights)
    if name == "buy_hold":
        return BuyAndHold(weights)
    if name == "fixed_weight":
        return FixedWeightRebalance(weights, config.get("rebalance_frequency", "monthly"))
    if name == "ma_band":
        return MABand(config.get("ma_window", 30), config.get("threshold", 0.05), weights,
                      config.get("buy_threshold"), config.get("sell_threshold"),
                      trade_mode=config.get("ma_trade_mode", "full_position"),
                      buy_amount=config.get("ma_buy_amount", 1000),
                      sell_fraction=config.get("ma_sell_fraction", 0.25),
                      funding_mode=config.get("ma_funding_mode", "cash"),
                      buy_first_only=config.get("ma_buy_first_only", False),
                      sell_first_only=config.get("ma_sell_first_only", False),
                      buy_budget_mode=config.get("ma_buy_budget_mode", "fixed"),
                      extra_amount=config.get("ma_extra_amount", 1000))
    if name == "cross_sectional_momentum":
        return CrossSectionalMomentum(config.get("momentum_lookback", 126),
                                      config.get("momentum_interval", 21), config.get("momentum_top_n", 1))
    raise ValueError(f"未知策略: {name}")


def dispersion(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {key: None for key in ("mean", "std", "min", "max", "positive_fraction")}
    scale = max(float(np.abs(values).max()), 1.0)
    scaled = values / scale
    return {"mean": float(scaled.mean() * scale), "std": float(scaled.std(ddof=0) * scale),
            "min": float(values.min()), "max": float(values.max()),
            "positive_fraction": float((values > 0).mean())}


def subperiod_analysis(engine, prices, strategy, count, weights=None):
    """等行情日划分、各段独立账户；信号可使用起点之前的行情，绝不读取段末之后数据。"""
    if not count:
        return pd.DataFrame(), {}
    prices = engine.pool.select_prices(prices)
    if count > len(prices) // 2:
        raise ValueError(f"{len(prices)} 个行情日不足以划分 {count} 个子区间，每段至少需 2 日")
    rows = []
    for number, indices in enumerate(np.array_split(np.arange(len(prices)), count), 1):
        start, end = prices.index[indices[0]], prices.index[indices[-1]]
        available = prices.loc[:end]
        result = engine.run(available, replace(strategy), start_date=start)
        benchmark = engine.run(available, BuyAndHold(weights), start_date=start)
        rows.append({"subperiod": number, **{key: result.summary[key] for key in
                    ("start", "end", "trading_days", "total_return", "cagr", "max_drawdown", "total_fees", "total_contributed", "total_pnl")},
                    "fills": len(result.fills), "benchmark_return": benchmark.summary["total_return"],
                    "excess_return": result.summary["total_return"] - benchmark.summary["total_return"]})
    frame = pd.DataFrame(rows)
    stats = {key: dispersion(frame[key]) for key in ("total_return", "cagr", "max_drawdown", "excess_return")}
    stats.update(count=count, mode="independent_accounts_with_prior_history",
                 no_trade_fraction=float(frame["fills"].eq(0).mean()),
                 std_definition="population_ddof_0")
    return frame, stats


def parameter_variants(strategy, fraction):
    fields = ("buy_threshold", "sell_threshold") if isinstance(strategy, MABand) else (
        ("lookback", "rebalance_interval") if isinstance(strategy, CrossSectionalMomentum) else ())
    for field in fields:
        base = (strategy.buy_deviation if field == "buy_threshold" else strategy.sell_deviation
                if field == "sell_threshold" else getattr(strategy, field))
        for direction in (-1, 1):
            # 离散参数至少改变一个行情日，不将“扰动”悄悄四舍五入回原值。
            value = base + direction * max(1, int(np.floor(base * fraction + 0.5))) if isinstance(base, int) else base * (1 + direction * fraction)
            yield field, base, value


def evaluate_robustness(engine, prices, strategy, result, config):
    count = config.get("subperiod_count", 0)
    result.subperiods, substats = subperiod_analysis(engine, prices, strategy, count, config.get("weights"))
    result.robustness = {
        "subperiods": substats,
        "notes": "历史样本内稳定性分析，不证明任意区间或未来有效；固定股票池存在幸存者偏差。无交易的平稳结果不代表有效。",
    }
    if substats:
        result.summary.update(subperiod_return_std=substats["total_return"]["std"],
                              subperiod_worst_return=substats["total_return"]["min"],
                              subperiod_positive_fraction=substats["total_return"]["positive_fraction"])
    if not config.get("sensitivity_enabled"):
        return result
    variants = list(parameter_variants(strategy, config["perturbation"]))
    if not variants:
        result.robustness["sensitivity"] = {"applicable": False, "reason": "当前仅支持均线和截面动量策略的参数扰动"}
        return result

    def row(parameter, base, value, evaluated, stats):
        summary = evaluated.summary
        return {"parameter": parameter, "base_value": base, "value": value, "status": "ok", "error": "",
                **{key: summary[key] for key in ("total_return", "cagr", "max_drawdown", "total_fees", "total_contributed", "total_pnl")},
                "return_delta": summary["total_return"] - result.summary["total_return"],
                "cagr_delta": summary["cagr"] - result.summary["cagr"] if summary["cagr"] is not None and result.summary["cagr"] is not None else None,
                "fills": len(evaluated.fills),
                "subperiod_return_std": stats.get("total_return", {}).get("std"),
                "subperiod_worst_return": stats.get("total_return", {}).get("min"),
                "subperiod_positive_fraction": stats.get("total_return", {}).get("positive_fraction")}

    rows = [row("baseline", None, None, result, substats)]
    for parameter, base, value in variants:
        try:
            varied = replace(strategy, **{parameter: value})
        except ValueError as exc:
            rows.append({"parameter": parameter, "base_value": base, "value": value, "status": "invalid", "error": str(exc)})
            continue
        evaluated = engine.run(prices, varied)
        _, stats = subperiod_analysis(engine, prices, varied, count, config.get("weights"))
        rows.append(row(parameter, base, value, evaluated, stats))
    result.sensitivity = pd.DataFrame(rows)
    valid = result.sensitivity.iloc[1:].loc[lambda f: f["status"] == "ok"]
    stats = {"applicable": True, "method": "one_at_a_time_relative", "perturbation": config["perturbation"],
             "valid_variants": len(valid), "invalid_variants": sum(r["status"] != "ok" for r in rows),
             "total_return": dispersion(valid["total_return"]),
             "worst_return_delta": float(valid["return_delta"].min()) if len(valid) else None}
    result.robustness["sensitivity"] = stats
    result.summary["sensitivity_worst_return_delta"] = stats["worst_return_delta"]
    return result


def add_research_arguments(parser, *, momentum=True):
    parser.add_argument("--ma-buy-first-only", action="store_true", help="买入条件首次满足时发出信号，连续满足不重复")
    parser.add_argument("--ma-sell-first-only", action="store_true", help="卖出条件首次满足时发出信号，连续满足不重复")
    parser.add_argument("--ma-buy-budget-mode", choices=("fixed", "cash_plus_extra"), default="fixed", help="固定买入预算或全部现金加额外投入")
    parser.add_argument("--ma-extra-amount", type=float, default=1000, help="全现金模式每个实际买入日额外投入，可为 0")
    parser.add_argument("--ma-trade-mode", choices=("full_position", "independent"), default="full_position", help="均线全仓进出或独立分批买卖")
    parser.add_argument("--ma-funding-mode", choices=("cash", "auto_contribute"), default="cash", help="仅用现有现金，或买入时自动追加不足资金")
    parser.add_argument("--ma-buy-amount", type=float, default=1000, help="独立买卖模式每次总买入预算，含费用；按股票池权重分配")
    parser.add_argument("--ma-sell-fraction", type=float, default=0.25, help="独立买卖每次卖出持仓比例，0.25 为 25%%")
    parser.add_argument("--buy-threshold", type=float, help="买入偏离比例，如 0.05；默认沿用 --threshold")
    parser.add_argument("--sell-threshold", type=float, help="卖出偏离比例，如 0.08；默认沿用 --threshold")
    if momentum:
        parser.add_argument("--dca-amount", type=float, default=1000, help="每期追加定投金额，含该期买入费用")
        parser.add_argument("--dca-frequency", choices=DCA_FREQUENCIES, default="monthly", help="定投周期，在新周期首个行情日执行")
        parser.add_argument("--momentum-lookback", type=int, default=126, help="动量回看行情日数")
        parser.add_argument("--momentum-interval", type=int, default=21, help="动量调仓间隔行情日数")
        parser.add_argument("--momentum-top-n", type=int, default=1, help="动量等权持有前 N 只")
    parser.add_argument("--subperiod-count", type=int, default=0, help="独立子区间数，0 关闭，2～50 启用")
    parser.add_argument("--sensitivity", dest="sensitivity_enabled", action="store_true", help="启用单因素参数扰动分析")
    parser.add_argument("--perturbation", type=float, default=0.1, help="相对扰动幅度，0.1 表示上下各 10%%")


def arguments_config(args):
    return research_config({key: value for key, value in vars(args).items() if value is not None})

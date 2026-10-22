"""多资产日线回测引擎：成交、持仓估值及策略时钟统一处理。"""

from types import MappingProxyType

import pandas as pd

from .account import FILL_COLUMNS, Account
from .analytics import equity_metrics, summarize
from .models import BacktestConfig, BacktestResult, StrategyContext
from .strategies import validate_targets

ORDER_COLUMNS = [
    "ticker",
    "target_weight",
    "signal_date",
    "execution_date",
    "status",
    "filled_quantity",
    "order_type",
    "budget",
    "sell_fraction",
    "allocation_weight",
]


class BacktestEngine:
    def __init__(self, pool, config=None):
        self.pool = pool
        self.config = config or BacktestConfig()

    def run(self, prices, strategy, *, start_date=None):
        # 某些股票可能在当前子区间结束后才上市；不能要求其在段内已有价格。
        prices = self.pool.select_prices(prices, allow_unquoted=start_date is not None)
        start = (
            0 if start_date is None
            else prices.index.searchsorted(pd.Timestamp(start_date))
        )
        trading_prices = prices.iloc[start:]
        if len(trading_prices) < 2:
            raise ValueError("回测子区间至少需要两个行情日")
        account = Account(self.pool, self.config)
        pending, orders = {}, []
        pending_buys, contributions = [], []
        pending_sells = []
        total_contributed = self.config.initial_cash
        history, positions = [], []
        marks = {}
        cash_plus_extra = getattr(strategy, "buy_budget_mode", "fixed") == "cash_plus_extra"
        auto_contribute = getattr(strategy, "funding_mode", "cash") == "auto_contribute" or cash_plus_extra
        if auto_contribute:
            contributions.append({"date": trading_prices.index[0], "kind": "initial",
                                  "amount": self.config.initial_cash,
                                  "total_contributed": total_contributed})

        def submit(targets, signal_date=pd.NaT):
            if targets is None:
                return
            for ticker, weight in validate_targets(targets, self.pool).items():
                if ticker in pending:
                    pending[ticker]["status"] = "superseded"
                order = {
                    "ticker": ticker,
                    "target_weight": float(weight),
                    "signal_date": signal_date,
                    "execution_date": pd.NaT,
                    "status": "pending",
                    "filled_quantity": 0.0,
                    "order_type": "target_weight",
                    "budget": None,
                }
                pending[ticker] = order
                orders.append(order)

        def submit_independent(context):
            hook = getattr(strategy, "on_close_orders", None)
            if hook is None:
                return
            buys, sells = hook(context)
            for side, values, queue in (("signal_buy_budget", buys, pending_buys),
                                        ("signal_sell_fraction", sells, pending_sells)):
                for ticker, value in values.items():
                    for previous in queue:
                        if previous["ticker"] == ticker and previous["status"] == "pending":
                            previous["status"] = "superseded"
                    order = dict(ticker=ticker, target_weight=None, signal_date=context.date,
                                 execution_date=pd.NaT, status="pending", filled_quantity=0.0,
                                 order_type=side, budget=value if side == "signal_buy_budget" else None,
                                 sell_fraction=value if side == "signal_sell_fraction" else None,
                                 allocation_weight=value if cash_plus_extra and side == "signal_buy_budget" else None)
                    if cash_plus_extra and side == "signal_buy_budget":
                        order["budget"] = None  # 到实际成交时才知道全部可用现金。
                    queue.append(order)
                    orders.append(order)

        submit(strategy.initial_targets(self.pool))
        if start:
            # 预热仅生成前一收盘信号；账户资金、成交和绩效从子区间起点计算。
            context = StrategyContext(
                date=prices.index[start - 1],
                history=prices.iloc[:start].copy(),
                pool=self.pool,
                cash=account.cash,
                equity=account.cash,
                quantities=MappingProxyType({t: 0.0 for t in self.pool.tickers}),
            )
            submit(strategy.on_close(context), prices.index[start - 1])
            submit_independent(context)
        previous_date = None
        for i, (date, quotes) in enumerate(trading_prices.iterrows(), start=start):
            marks.update(quotes.dropna().to_dict())
            contribution = 0.0
            pre_contribution_equity = float("nan")
            plan = getattr(strategy, "scheduled_investment", None)
            if plan:
                contribution, budgets = plan(date, previous_date, self.pool, self.config.initial_cash)
                if contribution:
                    pre_contribution_equity = account.equity(marks)
                account.cash += contribution
                total_contributed += contribution
                if previous_date is None or contribution:
                    contributions.append({"date": date, "kind": "initial" if previous_date is None else "recurring",
                                          "amount": self.config.initial_cash if previous_date is None else contribution,
                                          "total_contributed": total_contributed})
                for ticker, budget in budgets.items():
                    order = dict(ticker=ticker, target_weight=None, signal_date=date,
                                 execution_date=pd.NaT, status="pending", filled_quantity=0.0,
                                 order_type="buy_budget", budget=budget)
                    pending_buys.append(order)
                    orders.append(order)
            # 日历再平衡是预先制定的计划；与收盘信号分开处理。
            submit(strategy.scheduled_targets(date, previous_date, self.pool))
            ready = {
                ticker: order
                for ticker, order in pending.items()
                if pd.notna(quotes[ticker])
                and (pd.isna(order["signal_date"]) or order["signal_date"] < date)
            }
            fill_start = len(account.fills)
            before = account.equity(marks)
            ready_sells = [order for order in pending_sells
                           if order["status"] == "pending" and order["signal_date"] < date
                           and pd.notna(quotes[order["ticker"]])]
            if ready_sells:
                account.execute_fraction_sells(ready_sells, quotes, date)
            pending_sells = [order for order in pending_sells if order["status"] == "pending"]
            ready_buys = [order for order in pending_buys
                          if order["status"] == "pending" and pd.notna(quotes[order["ticker"]])
                          and (order["order_type"] == "buy_budget" or order["signal_date"] < date)]
            if ready_buys:
                if cash_plus_extra:
                    total_budget = account.cash + strategy.extra_amount
                    total_weight = sum(order["allocation_weight"] for order in ready_buys)
                    for order in ready_buys:
                        order["budget"] = total_budget * order["allocation_weight"] / total_weight
                if auto_contribute:
                    # 仅为当天可实际成交的买单补齐含费预算；优先使用已有现金和当日卖出回款。
                    added = strategy.extra_amount if cash_plus_extra else max(0.0, sum(order["budget"] for order in ready_buys) - account.cash)
                    if (cash_plus_extra and added > 0) or added > max(1.0, sum(order["budget"] for order in ready_buys)) * 1e-12:
                        pre_contribution_equity = account.equity(marks)
                        account.cash += added
                        contribution += added
                        total_contributed += added
                        before += added
                        contributions.append({"date": date, "kind": "signal_extra" if cash_plus_extra else "signal_top_up",
                                              "amount": added, "total_contributed": total_contributed})
                account.execute_budgets(ready_buys, quotes, date)
                if cash_plus_extra:
                    # 总预算就是全部现金；消除浮点舍入残余，避免之后产生幽灵小额买单。
                    account.cash = 0.0
                pending_buys = [order for order in pending_buys if order["status"] == "pending"]
            if ready:
                account.execute_targets(ready, quotes, marks, date)
                for ticker in ready:
                    del pending[ticker]
            daily_fills = account.fills[fill_start:]
            value = account.market_value(marks)
            cost_basis = sum(p.cost_basis for p in account.positions.values())
            history.append(
                {
                    "date": date,
                    "cash": account.cash,
                    "market_value": value,
                    "equity": account.cash + value,
                    "contribution": contribution,
                    "pre_contribution_equity": pre_contribution_equity,
                    "total_contributed": total_contributed,
                    "realized_pnl": account.realized_pnl,
                    "unrealized_pnl": value - cost_basis,
                    "fees": account.total_fees,
                    "cost": sum(fill["fee"] for fill in daily_fills),
                    "turnover": sum(fill["notional"] for fill in daily_fills)
                    / (2 * before)
                    if before > 0
                    else 0,
                }
            )
            for ticker, p in account.positions.items():
                mark = marks.get(ticker, float("nan"))
                market_value = p.quantity * mark if p.quantity else 0.0
                positions.append(
                    {
                        "date": date,
                        "ticker": ticker,
                        "close": quotes[ticker],
                        "valuation_price": mark,
                        "quantity": p.quantity,
                        "cost_basis": p.cost_basis,
                        "market_value": market_value,
                        "unrealized_pnl": market_value - p.cost_basis,
                    }
                )
            context = StrategyContext(
                date=date,
                history=prices.iloc[: i + 1].copy(),
                pool=self.pool,
                cash=account.cash,
                equity=account.cash + value,
                quantities=MappingProxyType(
                    {t: p.quantity for t, p in account.positions.items()}
                ),
            )
            submit(strategy.on_close(context), date)
            submit_independent(context)
            previous_date = date
        history = equity_metrics(
            pd.DataFrame(history).set_index("date"), self.config.initial_cash
        )
        trades = account.trade_records(prices.index[-1], marks)
        pending_count = len(pending) + sum(order["status"] == "pending" for order in pending_buys + pending_sells)
        summary = summarize(history, trades, self.config, strategy.name, pending_count)
        if getattr(strategy, "trade_mode", None):
            summary.update(ma_trade_mode=strategy.trade_mode, ma_buy_amount=strategy.buy_amount,
                           ma_sell_fraction=strategy.sell_fraction, ma_funding_mode=strategy.funding_mode,
                           ma_buy_first_only=strategy.buy_first_only, ma_sell_first_only=strategy.sell_first_only,
                           ma_buy_budget_mode=strategy.buy_budget_mode, ma_extra_amount=strategy.extra_amount)
        if auto_contribute:
            summary["return_method"] = "time_weighted"
        summary.update(
            {
                "pool": dict(self.pool.stocks),
                "fee_rate": self.config.fee_rate,
                "final_quantities": {
                    ticker: float(p.quantity) for ticker, p in account.positions.items()
                },
                "force_liquidate": False,
            }
        )
        return BacktestResult(
            history=history,
            positions=pd.DataFrame(positions),
            fills=pd.DataFrame(account.fills, columns=FILL_COLUMNS),
            trades=trades,
            orders=pd.DataFrame(orders, columns=ORDER_COLUMNS),
            summary=summary,
            contributions=pd.DataFrame(contributions),
        )

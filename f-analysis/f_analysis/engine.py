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
]


class BacktestEngine:
    def __init__(self, pool, config=None):
        self.pool = pool
        self.config = config or BacktestConfig()

    def run(self, prices, strategy):
        prices = self.pool.select_prices(prices)
        account = Account(self.pool, self.config)
        pending, orders = {}, []
        history, positions = [], []
        marks = {}

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
                }
                pending[ticker] = order
                orders.append(order)

        submit(strategy.initial_targets(self.pool))
        previous_date = None
        for i, (date, quotes) in enumerate(prices.iterrows()):
            marks.update(quotes.dropna().to_dict())
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
            previous_date = date
        history = equity_metrics(
            pd.DataFrame(history).set_index("date"), self.config.initial_cash
        )
        trades = account.trade_records(prices.index[-1], marks)
        summary = summarize(history, trades, self.config, strategy.name, len(pending))
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
        )

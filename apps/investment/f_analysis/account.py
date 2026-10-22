"""现金与平均成本持仓账本。策略不能直接修改账户。"""

from dataclasses import dataclass

import pandas as pd

TRADE_COLUMNS = [
    "ticker",
    "entry_signal_date",
    "entry_date",
    "entry_price",
    "quantity",
    "entry_fee",
    "entry_cost",
    "exit_signal_date",
    "exit_date",
    "exit_price",
    "exit_fee",
    "proceeds",
    "pnl",
    "return",
    "status",
    "holding_days",
]
FILL_COLUMNS = [
    "date",
    "signal_date",
    "ticker",
    "side",
    "price",
    "quantity",
    "notional",
    "fee",
    "realized_pnl",
]


@dataclass
class Position:
    quantity: float = 0.0
    cost_basis: float = 0.0
    gross_cost: float = 0.0
    entry_fees: float = 0.0
    entry_date: object = pd.NaT
    signal_date: object = pd.NaT


class Account:
    def __init__(self, pool, config):
        self.cash = float(config.initial_cash)
        self.fee_rate = config.fee_rate
        self.positions = {ticker: Position() for ticker in pool.tickers}
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.fills = []
        self.trades = []

    def market_value(self, marks):
        return sum(
            p.quantity * marks[t] for t, p in self.positions.items() if p.quantity > 0
        )

    def equity(self, marks):
        return self.cash + self.market_value(marks)

    def execute_budgets(self, orders, quotes, date):
        """固定含费预算买入，不因原持仓价格漂移触发卖出。"""
        required = sum(order["budget"] for order in orders)
        scale = min(1.0, self.cash / required) if required else 1.0
        for order in orders:
            ticker = order["ticker"]
            quantity = order["budget"] * scale / ((1 + self.fee_rate) * quotes[ticker])
            if quantity > 0:
                self.fill(ticker, quantity, quotes[ticker], date, order["signal_date"])
            order.update(execution_date=date, filled_quantity=quantity,
                         status="insufficient_cash" if quantity == 0 else
                         "filled" if scale >= 1 - 1e-12 else "partial")
        self.cash = max(0.0, self.cash)

    def execute_fraction_sells(self, orders, quotes, date):
        for order in orders:
            ticker = order["ticker"]
            quantity = self.positions[ticker].quantity * order["sell_fraction"]
            if quantity > 0:
                self.fill(ticker, -quantity, quotes[ticker], date, order["signal_date"])
            order.update(execution_date=date, filled_quantity=-quantity,
                         status="filled" if quantity > 0 else "no_change")

    def fill(self, ticker, signed_quantity, price, date, signal_date):
        p = self.positions[ticker]
        quantity = abs(signed_quantity)
        notional = quantity * price
        fee = notional * self.fee_rate
        realized = 0.0
        if signed_quantity > 0:
            if p.quantity == 0:
                p.entry_date, p.signal_date = date, signal_date
            self.cash -= notional + fee
            p.quantity += quantity
            p.cost_basis += notional + fee
            p.gross_cost += notional
            p.entry_fees += fee
            side = "buy"
        else:
            proportion = min(quantity / p.quantity, 1.0)
            basis = p.cost_basis * proportion
            realized = notional - fee - basis
            self.trades.append(
                {
                    "ticker": ticker,
                    "entry_signal_date": p.signal_date,
                    "entry_date": p.entry_date,
                    "entry_price": p.gross_cost / p.quantity,
                    "quantity": quantity,
                    "entry_fee": p.entry_fees * proportion,
                    "entry_cost": basis,
                    "exit_signal_date": signal_date,
                    "exit_date": date,
                    "exit_price": price,
                    "exit_fee": fee,
                    "proceeds": notional - fee,
                    "pnl": realized,
                    "return": realized / basis,
                    "status": "closed",
                    "holding_days": (date - p.entry_date).days,
                }
            )
            self.cash += notional - fee
            p.quantity -= quantity
            p.cost_basis -= basis
            p.gross_cost *= 1 - proportion
            p.entry_fees *= 1 - proportion
            if proportion == 1.0:
                self.positions[ticker] = Position()
            self.realized_pnl += realized
            side = "sell"
        self.total_fees += fee
        self.fills.append(
            {
                "date": date,
                "signal_date": signal_date,
                "ticker": ticker,
                "side": side,
                "price": price,
                "quantity": quantity,
                "notional": notional,
                "fee": fee,
                "realized_pnl": realized,
            }
        )
        return fee

    def execute_targets(self, targets, quotes, marks, date):
        """先卖后买；同日买单按资金需求等比例缩减，避免股票顺序影响分配。"""
        before = self.equity(marks)
        changes = {}
        for ticker, order in targets.items():
            desired_value = before * order["target_weight"]
            current = self.positions[ticker].quantity * quotes[ticker]
            delta = (desired_value - current) / quotes[ticker]
            changes[ticker] = (
                0.0 if abs(desired_value - current) < before * 1e-12 else delta
            )
        requested = changes.copy()
        for ticker, delta in changes.items():
            if delta < 0:
                order = targets[ticker]
                self.fill(ticker, delta, quotes[ticker], date, order["signal_date"])
        required = sum(
            delta * quotes[t] * (1 + self.fee_rate)
            for t, delta in changes.items()
            if delta > 0
        )
        scale = min(1.0, max(0.0, self.cash) / required) if required else 1.0
        for ticker, delta in changes.items():
            if delta > 0:
                filled = delta * scale
                if filled > 0:
                    self.fill(
                        ticker,
                        filled,
                        quotes[ticker],
                        date,
                        targets[ticker]["signal_date"],
                    )
                changes[ticker] = filled
        # 比例缩减保证没有透支；仅消除浮点累计产生的微小负数。
        if self.cash < -max(1.0, before) * 1e-10:
            raise RuntimeError("账户资金约束被违反")
        self.cash = max(0.0, self.cash)
        for ticker, order in targets.items():
            filled = changes[ticker]
            order.update({"execution_date": date, "filled_quantity": filled})
            if filled > 0 and scale < 1 - 1e-12:
                order["status"] = "partial"
            elif filled == 0 and requested[ticker] > 0:
                order["status"] = "insufficient_cash"
            else:
                order["status"] = "filled" if filled else "no_change"

    def trade_records(self, date, marks):
        rows = list(self.trades)
        for ticker, p in self.positions.items():
            if p.quantity > 0:
                pnl = p.quantity * marks[ticker] - p.cost_basis
                rows.append(
                    {
                        "ticker": ticker,
                        "entry_signal_date": p.signal_date,
                        "entry_date": p.entry_date,
                        "entry_price": p.gross_cost / p.quantity,
                        "quantity": p.quantity,
                        "entry_fee": p.entry_fees,
                        "entry_cost": p.cost_basis,
                        "pnl": pnl,
                        "return": pnl / p.cost_basis,
                        "status": "open",
                        "holding_days": (date - p.entry_date).days,
                    }
                )
        return pd.DataFrame(rows, columns=TRADE_COLUMNS)

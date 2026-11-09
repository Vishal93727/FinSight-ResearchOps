"""Event-driven long-only portfolio simulator with explicit next-close fills."""
from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd


@dataclass(frozen=True)
class FillEvent:
    timestamp: str
    symbol: str
    side: str
    shares: float
    reference_close: float
    fill_price: float
    notional: float
    commission: float
    slippage_cost: float


@dataclass(frozen=True)
class EventDrivenBacktestResult:
    ledger: pd.DataFrame
    fills: pd.DataFrame
    metrics: dict[str, float | int]


def run_event_driven_backtest(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    initial_cash: float = 100_000.0,
    commission_bps: float = 5.0,
    slippage_bps: float = 5.0,
    max_gross_exposure: float = 1.0,
    periods_per_year: int = 252,
) -> EventDrivenBacktestResult:
    """Simulate cash and share balances, processing queued target weights at next close.

    The weight observed at close(t) is converted into orders and filled at close(t+1).
    Existing holdings earn the close-to-close move ending at the fill timestamp; newly
    filled holdings begin earning returns on the following bar. Orders are long-only.
    """
    if initial_cash <= 0 or not math.isfinite(initial_cash):
        raise ValueError("initial_cash must be finite and positive")
    if commission_bps < 0 or slippage_bps < 0 or commission_bps > 500 or slippage_bps > 500:
        raise ValueError("Commission and slippage must be within [0, 500] bps")
    if not 0 < max_gross_exposure <= 1 or periods_per_year <= 0:
        raise ValueError("Invalid gross-exposure or annualization setting")
    if prices.empty or not prices.columns.is_unique or set(prices.columns) != set(target_weights.columns):
        raise ValueError("Price and weight frames must contain the same non-empty asset columns")

    px = prices.copy().sort_index()
    weights = target_weights.reindex(index=px.index, columns=px.columns).copy()
    px.index = pd.to_datetime(px.index, errors="raise", utc=True)
    weights.index = pd.to_datetime(weights.index, errors="raise", utc=True)
    if px.index.has_duplicates or not px.index.is_monotonic_increasing:
        raise ValueError("Price index must contain unique, increasing timestamps")
    px = px.apply(pd.to_numeric, errors="raise").astype(float)
    weights = weights.apply(pd.to_numeric, errors="raise").astype(float)
    if not px.map(math.isfinite).all().all() or (px <= 0).any().any():
        raise ValueError("Prices must be finite and positive")
    if not weights.map(math.isfinite).all().all() or (weights < 0).any().any():
        raise ValueError("Target weights must be finite and non-negative")
    if (weights.sum(axis=1) > max_gross_exposure + 1e-9).any():
        raise ValueError("Target gross exposure exceeds the configured risk limit")

    cash = float(initial_cash)
    shares = {symbol: 0.0 for symbol in px.columns}
    pending_weights: pd.Series | None = None
    previous_nav = float(initial_cash)
    ledger_rows: list[dict] = []
    fill_rows: list[dict] = []
    cost_rate = (commission_bps + slippage_bps) / 10_000.0
    commission_rate = commission_bps / 10_000.0
    slippage_rate = slippage_bps / 10_000.0

    for timestamp, row in px.iterrows():
        close_prices = row.to_dict()
        nav_before_fill = cash + sum(shares[symbol] * close_prices[symbol] for symbol in px.columns)
        if not math.isfinite(nav_before_fill) or nav_before_fill <= 0:
            raise ValueError("Portfolio equity became non-positive; simulation halted")
        commissions = 0.0
        slippage_costs = 0.0
        turnover = 0.0

        if pending_weights is not None:
            gross_target = float(pending_weights.sum())
            # Reserve the maximum proportional execution cost so a 100%-gross target
            # cannot create negative cash solely from commissions and slippage.
            deployable_nav = nav_before_fill * (1.0 - cost_rate * gross_target)
            orders: list[tuple[str, str, float, float]] = []
            for symbol in px.columns:
                reference_close = float(close_prices[symbol])
                current_value = shares[symbol] * reference_close
                target_value = deployable_nav * float(pending_weights[symbol])
                delta_value = target_value - current_value
                if abs(delta_value) > 1e-10:
                    orders.append(("BUY" if delta_value > 0 else "SELL", symbol, delta_value, reference_close))
            # Sell reductions first so proceeds are available to fund buys in a rotation.
            orders.sort(key=lambda order: 0 if order[0] == "SELL" else 1)
            for side, symbol, delta_value, reference_close in orders:
                fill_price = reference_close * (1.0 + slippage_rate if side == "BUY" else 1.0 - slippage_rate)
                trade_shares = delta_value / fill_price
                notional = abs(trade_shares * fill_price)
                commission = notional * commission_rate
                slippage_cost = abs(trade_shares) * abs(fill_price - reference_close)
                cash -= trade_shares * fill_price + commission
                shares[symbol] += trade_shares
                commissions += commission
                slippage_costs += slippage_cost
                turnover += notional / max(nav_before_fill, 1e-12)
                fill_rows.append({
                    "timestamp": timestamp.isoformat(), "symbol": symbol, "side": side,
                    "shares": trade_shares, "reference_close": reference_close,
                    "fill_price": fill_price, "notional": notional,
                    "commission": commission, "slippage_cost": slippage_cost,
                })
            if cash < -max(1e-6, initial_cash * 1e-9):
                raise ValueError("Execution would create a negative cash balance")
            cash = max(cash, 0.0)

        holdings_value = sum(shares[symbol] * close_prices[symbol] for symbol in px.columns)
        nav = cash + holdings_value
        if nav <= 0 or not math.isfinite(nav):
            raise ValueError("Portfolio equity became non-positive; simulation halted")
        gross_exposure = holdings_value / nav if nav > 0 else 0.0
        daily_return = nav / previous_nav - 1.0
        ledger_rows.append({
            "date": timestamp, "cash": cash, "holdings_value": holdings_value,
            "equity": nav, "portfolio_return": daily_return,
            "gross_exposure": gross_exposure, "turnover": turnover,
            "commission": commissions, "slippage_cost": slippage_costs,
            "total_execution_cost": commissions + slippage_costs,
        })
        previous_nav = nav
        pending_weights = weights.loc[timestamp]

    ledger = pd.DataFrame(ledger_rows)
    ledger["drawdown"] = ledger["equity"] / ledger["equity"].cummax() - 1.0
    returns = ledger["portfolio_return"]
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    mean_return = float(returns.mean()) if len(returns) else 0.0
    ending_equity = float(ledger["equity"].iloc[-1])
    metrics: dict[str, float | int] = {
        "total_return": ending_equity / initial_cash - 1.0,
        "annualized_return": (ending_equity / initial_cash) ** (periods_per_year / max(len(returns), 1)) - 1.0,
        "annualized_volatility": volatility * math.sqrt(periods_per_year),
        "sharpe_ratio": mean_return / volatility * math.sqrt(periods_per_year) if volatility > 0 else 0.0,
        "max_drawdown": float(ledger["drawdown"].min()),
        "total_turnover": float(ledger["turnover"].sum()),
        "turnover": float(ledger["turnover"].sum()),
        "average_gross_exposure": float(ledger["gross_exposure"].mean()),
        "estimated_cost_bps": float(ledger["total_execution_cost"].sum() / initial_cash * 10_000.0),
        "observations": int(len(ledger)),
        "fill_count": int(len(fill_rows)),
    }
    return EventDrivenBacktestResult(
        ledger=ledger,
        fills=pd.DataFrame(fill_rows, columns=["timestamp", "symbol", "side", "shares", "reference_close",
                                               "fill_price", "notional", "commission", "slippage_cost"]),
        metrics=metrics,
    )

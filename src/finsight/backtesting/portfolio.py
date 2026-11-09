"""Deterministic multi-asset portfolio accounting with close-to-next-close execution."""
from __future__ import annotations
from dataclasses import dataclass
import math
import pandas as pd


@dataclass(frozen=True)
class PortfolioBacktestResult:
    ledger: pd.DataFrame
    metrics: dict[str, float | int]


def run_portfolio_backtest(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    commission_bps: float = 5.0,
    slippage_bps: float = 5.0,
    max_gross_exposure: float = 1.0,
    periods_per_year: int = 252,
) -> PortfolioBacktestResult:
    """Backtest close-time target weights filled at the next close.

    Returns start accruing only after the fill close. Unallocated capital remains cash;
    short positions and leverage above the configured gross cap are rejected.
    """
    if commission_bps < 0 or slippage_bps < 0 or commission_bps > 500 or slippage_bps > 500:
        raise ValueError("Commission and slippage must be within [0, 500] bps")
    if not 0 < max_gross_exposure <= 1.0:
        raise ValueError("max_gross_exposure must be within (0, 1]")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    if prices.empty or prices.shape[1] == 0 or not prices.columns.is_unique:
        raise ValueError("Prices must contain at least one asset with unique columns")
    if set(prices.columns) != set(target_weights.columns):
        raise ValueError("Price and target-weight asset columns must match exactly")
    px = prices.copy().sort_index()
    weights = target_weights.reindex(index=px.index, columns=px.columns).copy()
    px.index = pd.to_datetime(px.index, errors="raise", utc=True)
    weights.index = pd.to_datetime(weights.index, errors="raise", utc=True)
    if px.index.has_duplicates or not px.index.is_monotonic_increasing:
        raise ValueError("Price index must contain unique, increasing dates")
    px = px.apply(pd.to_numeric, errors="raise").astype(float)
    weights = weights.apply(pd.to_numeric, errors="raise").astype(float)
    if not px.map(math.isfinite).all().all() or (px <= 0).any().any():
        raise ValueError("Prices must be finite and positive")
    if not weights.map(math.isfinite).all().all():
        raise ValueError("Target weights must be finite")
    if (weights < 0).any().any():
        raise ValueError("Short weights are not supported")
    gross_target = weights.sum(axis=1)
    if (gross_target > max_gross_exposure + 1e-9).any():
        raise ValueError("Target gross exposure exceeds the configured risk limit")

    # Signal at close(t) => fill at close(t+1) => first return is close(t+1) to close(t+2).
    filled_weights = weights.shift(1).fillna(0.0)
    held_weights = filled_weights.shift(1).fillna(0.0)
    asset_returns = px.pct_change().fillna(0.0)
    turnover = filled_weights.diff().abs().sum(axis=1)
    turnover.iloc[0] = float(filled_weights.iloc[0].abs().sum())
    costs = turnover * ((commission_bps + slippage_bps) / 10_000.0)
    portfolio_return = (held_weights * asset_returns).sum(axis=1) - costs
    ledger = pd.DataFrame({
        "date": px.index,
        "portfolio_return": portfolio_return.to_numpy(),
        "turnover": turnover.to_numpy(),
        "trading_cost": costs.to_numpy(),
        "gross_exposure": filled_weights.sum(axis=1).to_numpy(),
        "cash_weight": (1.0 - filled_weights.sum(axis=1)).to_numpy(),
    })
    ledger["equity"] = (1.0 + ledger["portfolio_return"]).cumprod()
    ledger["drawdown"] = ledger["equity"] / ledger["equity"].cummax() - 1.0
    vol = float(ledger["portfolio_return"].std(ddof=1)) if len(ledger) > 1 else 0.0
    mean = float(ledger["portfolio_return"].mean()) if len(ledger) else 0.0
    sharpe = mean / vol * math.sqrt(periods_per_year) if vol > 0 else 0.0
    equity_end = float(ledger["equity"].iloc[-1])
    metrics: dict[str, float | int] = {
        "total_return": equity_end - 1.0,
        "annualized_return": equity_end ** (periods_per_year / max(len(ledger), 1)) - 1.0 if equity_end > 0 else -1.0,
        "annualized_volatility": vol * math.sqrt(periods_per_year),
        "sharpe_ratio": sharpe,
        "max_drawdown": float(ledger["drawdown"].min()),
        "total_turnover": float(turnover.sum()),
        "estimated_cost_bps": float(costs.sum() * 10_000.0),
        "average_gross_exposure": float(ledger["gross_exposure"].mean()),
        "observations": int(len(ledger)),
    }
    return PortfolioBacktestResult(ledger=ledger, metrics=metrics)

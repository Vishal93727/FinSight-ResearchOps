"""Deterministic long-only backtest engine with next-bar execution and trading costs."""
from dataclasses import dataclass
import math
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Backtest time series and summary metrics."""
    equity_curve: pd.DataFrame
    metrics: dict[str, float | int]


def run_long_only_backtest(
    bars: pd.DataFrame,
    signal: pd.Series,
    *,
    commission_bps: float = 5.0,
    slippage_bps: float = 5.0,
    periods_per_year: int = 252,
    evaluation_start: str | pd.Timestamp | None = None,
    evaluation_end: str | pd.Timestamp | None = None,
) -> BacktestResult:
    """Apply close(t) signals from the next bar and deduct costs on position changes.

    A signal formed at close(t) is filled at close(t+1). Because close-to-close bars
    cannot earn the return ending at that fill close, P&L starts on the subsequent bar.
    This conservative convention avoids attributing the overnight gap to a close-time
    signal. Signals must be long-only weights in [0, 1].
    """
    required = {"date", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Missing backtest columns: {', '.join(sorted(missing))}")
    if commission_bps < 0 or slippage_bps < 0 or commission_bps > 500 or slippage_bps > 500 or periods_per_year <= 0:
        raise ValueError("Costs must be between 0 and 500 bps and periods_per_year must be positive")
    frame = bars.loc[:, ["date", "close"]].copy()
    signal_values = list(signal)
    if len(signal_values) != len(frame):
        raise ValueError("Signal must have one value per bar")
    frame["_input_signal"] = signal_values
    frame["date"] = pd.to_datetime(frame["date"], errors="raise", utc=True)
    frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    if frame["date"].isna().any():
        raise ValueError("Backtest dates must be present")
    if not frame["close"].map(math.isfinite).all():
        raise ValueError("Close prices must be finite numbers")
    frame = frame.sort_values("date").reset_index(drop=True)
    if len(frame) < 2:
        raise ValueError("At least two bars are required")
    if frame["date"].duplicated().any():
        raise ValueError("Duplicate dates are not allowed")
    if (frame["close"] <= 0).any():
        raise ValueError("Close prices must be positive")
    try:
        aligned_signal = pd.to_numeric(frame.pop("_input_signal"), errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Signal must contain numeric weights") from exc
    if len(aligned_signal) != len(frame) or aligned_signal.isna().any() or not aligned_signal.map(math.isfinite).all():
        raise ValueError("Signal must have one finite value per bar")
    if not aligned_signal.between(0.0, 1.0).all():
        raise ValueError("Long-only signal weights must be within [0, 1]")

    frame["signal"] = aligned_signal.to_numpy()
    frame["asset_return"] = frame["close"].pct_change().fillna(0.0)
    frame["filled_position"] = frame["signal"].shift(1).fillna(0.0)
    frame["turnover"] = frame["filled_position"].diff().abs().fillna(frame["filled_position"].abs())
    frame["executed_position"] = frame["filled_position"].shift(1).fillna(0.0)
    cost_rate = (commission_bps + slippage_bps) / 10_000.0
    frame["trading_cost"] = frame["turnover"] * cost_rate
    frame["strategy_return"] = frame["executed_position"] * frame["asset_return"] - frame["trading_cost"]
    evaluation = frame
    if evaluation_start is not None:
        start = pd.to_datetime(evaluation_start, utc=True)
        evaluation = evaluation.loc[evaluation["date"] >= start]
    if evaluation_end is not None:
        end = pd.to_datetime(evaluation_end, utc=True)
        evaluation = evaluation.loc[evaluation["date"] <= end]
    evaluation = evaluation.copy().reset_index(drop=True)
    if evaluation.empty:
        raise ValueError("No bars fall inside the requested evaluation window")
    evaluation["equity"] = (1.0 + evaluation["strategy_return"]).cumprod()
    evaluation["drawdown"] = evaluation["equity"] / evaluation["equity"].cummax() - 1.0

    returns = evaluation["strategy_return"]
    volatility = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    mean_return = float(returns.mean()) if len(returns) else 0.0
    sharpe = mean_return / volatility * math.sqrt(periods_per_year) if volatility > 0 else 0.0
    equity_end = float(evaluation["equity"].iloc[-1])
    annualized_return = equity_end ** (periods_per_year / max(len(returns), 1)) - 1.0 if equity_end > 0 else -1.0
    metrics: dict[str, float | int] = {
        "total_return": equity_end - 1.0,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility * math.sqrt(periods_per_year),
        "sharpe_ratio": sharpe,
        "max_drawdown": float(evaluation["drawdown"].min()),
        "turnover": float(evaluation["turnover"].sum()),
        "estimated_cost_bps": float(evaluation["trading_cost"].sum() * 10_000.0),
        "average_gross_exposure": float(evaluation["executed_position"].mean()),
        "observations": int(len(returns)),
    }
    return BacktestResult(equity_curve=evaluation, metrics=metrics)

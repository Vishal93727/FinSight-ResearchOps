"""Frozen, versioned, point-in-time trading universe.

The filter-then-deduplicate-then-freeze flow follows the universe constructor in
``niharmaddina/quant-strategy-framework`` (MIT). That reference reads *today's* market cap and
average volume from a live data vendor, which injects look-ahead and survivorship bias into any
historical test. This module keeps the flow but computes every criterion only from bars dated
strictly before ``as_of``, records why each symbol was excluded, and fingerprints the result so
a backtest can prove the universe never changed after the experiment was defined.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"symbol", "date", "close", "volume"}


@dataclass(frozen=True)
class UniverseRules:
    min_history_bars: int = 60
    min_price: float = 5.0
    min_median_dollar_volume: float = 1_000_000.0
    liquidity_window: int = 60
    max_missing_fraction: float = 0.05
    max_correlation: float = 0.90
    max_symbols: int | None = None

    def __post_init__(self) -> None:
        if self.min_history_bars < 20 or self.liquidity_window < 5:
            raise ValueError("min_history_bars must be >= 20 and liquidity_window >= 5")
        if not 0.0 <= self.max_missing_fraction < 1.0 or not 0.0 < self.max_correlation <= 1.0:
            raise ValueError("max_missing_fraction must be in [0, 1) and max_correlation in (0, 1]")
        if self.max_symbols is not None and self.max_symbols < 1:
            raise ValueError("max_symbols must be positive")


@dataclass(frozen=True)
class FrozenUniverse:
    name: str
    as_of: str
    rules: dict
    symbols: tuple[str, ...]
    excluded: dict[str, str]
    fingerprint: str

    def verify(self) -> None:
        if _fingerprint(self.name, self.as_of, self.rules, self.symbols) != self.fingerprint:
            raise ValueError("frozen universe was modified after it was built")

    def assert_contains_only(self, symbols) -> None:
        """Raise if a backtest or experiment uses a symbol outside the frozen universe."""
        extra = sorted(set(symbols) - set(self.symbols))
        if extra:
            raise ValueError(f"symbols outside the frozen universe: {extra}")


def _fingerprint(name: str, as_of: str, rules: dict, symbols) -> str:
    payload = json.dumps({"name": name, "as_of": as_of, "rules": rules, "symbols": list(symbols)},
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def build_frozen_universe(bars: pd.DataFrame, as_of, rules: UniverseRules | None = None, *,
                          candidates: list[str] | None = None, name: str = "universe") -> FrozenUniverse:
    """Select symbols using only data dated before ``as_of`` and freeze the result.

    Order of filters: history, missing data, price, liquidity (median dollar volume), then
    correlation de-duplication that keeps the more liquid of any highly correlated pair.
    """
    rules = rules or UniverseRules()
    missing_columns = REQUIRED_COLUMNS - set(bars.columns)
    if missing_columns:
        raise ValueError(f"bars is missing columns: {sorted(missing_columns)}")
    cutoff = pd.Timestamp(as_of)
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    frame = frame[frame["date"] < cutoff]  # strictly before: nothing from the decision day or later
    if frame.empty:
        raise ValueError("no bars exist before as_of")
    wanted = sorted(set(candidates)) if candidates is not None else sorted(frame["symbol"].unique())
    calendar = pd.DatetimeIndex(sorted(frame["date"].unique()))
    excluded: dict[str, str] = {}
    liquidity: dict[str, float] = {}
    closes: dict[str, pd.Series] = {}
    for symbol in wanted:
        rows = frame[frame["symbol"] == symbol].drop_duplicates("date").sort_values("date")
        if len(rows) < rules.min_history_bars:
            excluded[symbol] = f"history below {rules.min_history_bars} bars"
            continue
        span = calendar[calendar >= rows["date"].iloc[0]]
        missing = 1.0 - len(rows) / max(len(span), 1)
        if missing > rules.max_missing_fraction:
            excluded[symbol] = f"missing {missing:.1%} of bars since first observation"
            continue
        recent = rows.tail(rules.liquidity_window)
        if float(recent["close"].iloc[-1]) < rules.min_price:
            excluded[symbol] = f"last close below {rules.min_price}"
            continue
        dollar_volume = float((recent["close"] * recent["volume"]).median())
        if dollar_volume < rules.min_median_dollar_volume:
            excluded[symbol] = "median dollar volume below minimum"
            continue
        liquidity[symbol] = dollar_volume
        closes[symbol] = rows.set_index("date")["close"].astype(float)

    kept = sorted(liquidity, key=lambda s: (-liquidity[s], s))
    if len(kept) > 1:
        returns = pd.DataFrame({s: np.log(closes[s]).diff() for s in kept}).dropna(how="all")
        corr = returns.corr()
        selected: list[str] = []
        for symbol in kept:  # most liquid first, so the more liquid of a correlated pair survives
            clash = next((c for c in selected if pd.notna(corr.loc[symbol, c])
                          and abs(corr.loc[symbol, c]) > rules.max_correlation), None)
            if clash is None:
                selected.append(symbol)
            else:
                excluded[symbol] = f"correlation with {clash} above {rules.max_correlation}"
        kept = selected
    if rules.max_symbols is not None and len(kept) > rules.max_symbols:
        for symbol in kept[rules.max_symbols:]:
            excluded[symbol] = f"outside the top {rules.max_symbols} by liquidity"
        kept = kept[: rules.max_symbols]
    symbols = tuple(sorted(kept))
    rule_dict = asdict(rules)
    as_of_text = cutoff.isoformat()
    return FrozenUniverse(name, as_of_text, rule_dict, symbols, dict(sorted(excluded.items())),
                          _fingerprint(name, as_of_text, rule_dict, symbols))


def survivorship_report(universe: FrozenUniverse, bars: pd.DataFrame) -> dict:
    """List frozen members whose data stops before the end of the sample.

    These names must stay in the evaluation (they are what a survivor-only list would hide).
    """
    frame = bars[bars["symbol"].isin(universe.symbols)].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    last_date = frame["date"].max()
    last_by_symbol = frame.groupby("symbol")["date"].max()
    ended = {s: str(d.date()) for s, d in last_by_symbol.items() if d < last_date}
    return {"sample_end": str(last_date.date()), "members": len(universe.symbols),
            "members_with_early_end": ended, "survivor_only_bias_risk": bool(ended)}

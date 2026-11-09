"""Frozen point-in-time universe, the Bollinger baseline, and frozen-results regression."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from finsight.backtesting.engine import run_long_only_backtest
from finsight.backtesting.universe import UniverseRules, build_frozen_universe, survivorship_report
from finsight.models.baselines.strategies import BASELINE_STRATEGIES, bollinger_mean_reversion_signal

FIXTURE = Path(__file__).parent / "fixtures" / "baseline_regression.json"


def _market(days: int = 160) -> pd.DataFrame:
    """Deterministic multi-symbol market with one illiquid, one cheap, one short and one duplicate name."""
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2023-01-02", periods=days, tz="UTC")
    market = np.cumsum(rng.normal(0, 0.01, days))
    frames = []

    def add(symbol, drift, noise, price0, volume, start=0, end=None, base=None):
        path = np.cumsum(rng.normal(drift, noise, days)) if base is None else base + rng.normal(0, 0.0005, days).cumsum()
        close = price0 * np.exp(path)
        frame = pd.DataFrame({"symbol": symbol, "date": dates, "close": close, "volume": volume})
        frames.append(frame.iloc[start:end])

    add("AAA", 0.0004, 0.012, 100, 2_000_000)
    add("BBB", 0.0002, 0.015, 50, 3_000_000)
    add("CLONE", 0, 0, 100, 1_000_000, base=market * 0 + np.log(frames[0]["close"].to_numpy() / 100))
    add("PENNY", 0.0, 0.02, 2.0, 5_000_000)
    add("THIN", 0.0003, 0.01, 40, 100)
    add("SHORT", 0.0003, 0.01, 40, 2_000_000, start=130)
    add("DELIST", 0.0002, 0.013, 60, 1_500_000, end=155)  # data stops after the freeze date
    add("GONE", 0.0002, 0.013, 60, 1_500_000, end=140)  # already stale at the freeze date
    return pd.concat(frames, ignore_index=True)


def test_each_exclusion_has_a_recorded_reason_and_the_survivors_are_sorted():
    universe = build_frozen_universe(_market(), "2023-08-01", UniverseRules(max_correlation=0.98))
    assert "PENNY" in universe.excluded and "last close below" in universe.excluded["PENNY"]
    assert "median dollar volume" in universe.excluded["THIN"]
    assert "history below" in universe.excluded["SHORT"]
    assert "missing" in universe.excluded["GONE"]
    assert any("correlation with AAA" in reason for symbol, reason in universe.excluded.items() if symbol == "CLONE")
    assert universe.symbols == tuple(sorted(universe.symbols))
    assert {"AAA", "BBB", "DELIST"} <= set(universe.symbols)


def test_selection_ignores_data_on_or_after_the_as_of_date():
    market = _market()
    as_of = "2023-08-01"
    base = build_frozen_universe(market, as_of, UniverseRules(max_correlation=0.98))
    later = market.copy()
    mask = pd.to_datetime(later["date"], utc=True) >= pd.Timestamp(as_of, tz="UTC")
    later.loc[mask & (later["symbol"] == "AAA"), "close"] = 0.01  # a collapse after the freeze date
    later.loc[mask & (later["symbol"] == "AAA"), "volume"] = 1
    assert build_frozen_universe(later, as_of, UniverseRules(max_correlation=0.98)).fingerprint == base.fingerprint


def test_fingerprint_detects_tampering_and_outside_symbols_are_rejected():
    universe = build_frozen_universe(_market(), "2023-08-01", UniverseRules(max_correlation=0.98))
    universe.verify()
    universe.assert_contains_only(universe.symbols[:2])
    with pytest.raises(ValueError, match="outside the frozen universe"):
        universe.assert_contains_only([*universe.symbols, "NEWLISTING"])
    forged = type(universe)(universe.name, universe.as_of, universe.rules, (*universe.symbols, "NEWLISTING"),
                            universe.excluded, universe.fingerprint)
    with pytest.raises(ValueError, match="modified"):
        forged.verify()


def test_symbol_cap_keeps_the_most_liquid_names():
    universe = build_frozen_universe(_market(), "2023-08-01", UniverseRules(max_correlation=0.98, max_symbols=2))
    assert len(universe.symbols) == 2
    assert any("top 2" in reason for reason in universe.excluded.values())


def test_survivorship_report_keeps_names_whose_data_ends_early():
    market = _market()
    universe = build_frozen_universe(market, "2023-08-01", UniverseRules(max_correlation=0.98))
    report = survivorship_report(universe, market)
    assert "DELIST" in report["members_with_early_end"] and report["survivor_only_bias_risk"] is True


def test_invalid_rules_and_inputs_are_rejected():
    with pytest.raises(ValueError):
        UniverseRules(max_correlation=1.5)
    with pytest.raises(ValueError):
        build_frozen_universe(_market().drop(columns=["volume"]), "2023-08-01")
    with pytest.raises(ValueError):
        build_frozen_universe(_market(), "2000-01-01")


# --- Bollinger baseline ----------------------------------------------------------------------

def _bars(closes) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.bdate_range("2024-01-02", periods=len(closes), tz="UTC"), "close": closes})


def test_bollinger_enters_below_the_lower_band_and_exits_at_the_mean():
    closes = [100.0] * 25 + [80.0, 81.0, 90.0, 100.0, 104.0, 100.0]
    signal = bollinger_mean_reversion_signal(_bars(closes), window=20, entry_z=2.0)
    assert signal.iloc[24] == 0.0
    assert signal.iloc[25] == 1.0  # the plunge bar is itself the signal bar; the engine fills it later
    assert signal.iloc[-1] == 0.0
    assert set(signal.unique()) <= {0.0, 1.0}


def test_bollinger_uses_only_past_closes_and_validates_inputs():
    closes = list(100 + np.sin(np.arange(60)))
    full = bollinger_mean_reversion_signal(_bars(closes))
    truncated = bollinger_mean_reversion_signal(_bars(closes[:40]))
    assert full.iloc[:40].tolist() == truncated.tolist()
    with pytest.raises(ValueError):
        bollinger_mean_reversion_signal(_bars(closes), window=2)
    with pytest.raises(ValueError):
        bollinger_mean_reversion_signal(_bars(closes), entry_z=1.0, exit_z=1.5)
    assert "bollinger_mean_reversion" in BASELINE_STRATEGIES


# --- frozen-results regression ---------------------------------------------------------------

def _regression_bars() -> pd.DataFrame:
    rng = np.random.default_rng(2024)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, 400)))
    return pd.DataFrame({"date": pd.bdate_range("2022-01-03", periods=400, tz="UTC"), "close": close})


def _regression_results() -> dict:
    bars = _regression_bars()
    results = {}
    for name, strategy in sorted(BASELINE_STRATEGIES.items()):
        metrics = run_long_only_backtest(bars, strategy(bars), commission_bps=5, slippage_bps=5).metrics
        results[name] = {key: round(float(value), 8) for key, value in sorted(metrics.items())}
    return results


def test_baseline_results_match_the_committed_frozen_results():
    """Fails on any unintended change to signal or engine semantics. Regenerate on purpose:
    FINSIGHT_UPDATE_REGRESSION=1 pytest backend/tests/test_phase6_universe_and_baselines.py"""
    import os

    actual = _regression_results()
    if os.environ.get("FINSIGHT_UPDATE_REGRESSION") == "1":
        FIXTURE.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    expected = json.loads(FIXTURE.read_text())
    assert set(actual) == set(expected)
    for name in expected:
        for key, value in expected[name].items():
            assert actual[name][key] == pytest.approx(value, abs=1e-6), (name, key)

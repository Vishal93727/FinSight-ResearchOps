"""Deterministic, long-only baseline strategy signal registry."""
import pandas as pd


def buy_and_hold_signal(bars: pd.DataFrame) -> pd.Series:
    """Return a fully-invested long-only signal at each observed close."""
    if "close" not in bars:
        raise ValueError("close column is required")
    return pd.Series(1.0, index=bars.index, name="signal")


def moving_average_crossover_signal(
    bars: pd.DataFrame, short_window: int = 5, long_window: int = 20,
) -> pd.Series:
    """Return 1 when short moving average exceeds long moving average, else 0."""
    if "close" not in bars:
        raise ValueError("close column is required")
    if short_window < 2 or long_window <= short_window:
        raise ValueError("Require 2 <= short_window < long_window")
    close = pd.to_numeric(bars["close"], errors="raise")
    short_ma = close.rolling(short_window, min_periods=short_window).mean()
    long_ma = close.rolling(long_window, min_periods=long_window).mean()
    return (short_ma > long_ma).fillna(False).astype(float).rename("signal")


def rsi_mean_reversion_signal(
    bars: pd.DataFrame, *, window: int = 14, oversold: float = 30.0, overbought: float = 70.0,
) -> pd.Series:
    """Enter when RSI reaches oversold and exit when it reaches overbought.

    Signals use only close data available at the signal timestamp. The backtest engine
    applies them at the following bar, so the strategy does not trade on the same close.
    """
    if "close" not in bars:
        raise ValueError("close column is required")
    if window < 2 or not 0 < oversold < overbought < 100:
        raise ValueError("Invalid RSI window or thresholds")
    close = pd.to_numeric(bars["close"], errors="raise").astype(float)
    delta = close.diff()
    gains = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    losses = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    relative_strength = gains / losses.where(losses > 0)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((losses == 0) & (gains > 0), 100.0)
    rsi = rsi.mask((losses == 0) & (gains == 0), 50.0)
    signal = pd.Series(0.0, index=bars.index, name="signal")
    holding = 0.0
    for index, value in enumerate(rsi):
        if pd.notna(value):
            if value <= oversold:
                holding = 1.0
            elif value >= overbought:
                holding = 0.0
        signal.iloc[index] = holding
    return signal


def bollinger_mean_reversion_signal(
    bars: pd.DataFrame, *, window: int = 20, entry_z: float = 2.0, exit_z: float = 0.0,
) -> pd.Series:
    """Enter below the lower Bollinger band and exit when price returns to the mean.

    The z-score of the close against its trailing mean and standard deviation (the same
    ingredients as the Bollinger-band mean-reversion strategy in niharmaddina/
    quant-strategy-framework, MIT) uses only closes up to the signal bar. Long-only; the
    engine fills the signal on the following bar.
    """
    if "close" not in bars:
        raise ValueError("close column is required")
    if window < 5 or entry_z <= 0 or exit_z >= entry_z:
        raise ValueError("Invalid window or z-score thresholds")
    close = pd.to_numeric(bars["close"], errors="raise").astype(float)
    mean = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    zscore = (close - mean) / std.where(std > 0)
    signal = pd.Series(0.0, index=bars.index, name="signal")
    holding = 0.0
    for index, value in enumerate(zscore):
        if pd.notna(value):
            if value <= -entry_z:
                holding = 1.0
            elif value >= -exit_z:
                holding = 0.0
        signal.iloc[index] = holding
    return signal


BASELINE_STRATEGIES = {
    "buy_and_hold": buy_and_hold_signal,
    "moving_average_crossover": moving_average_crossover_signal,
    "rsi_mean_reversion": rsi_mean_reversion_signal,
    "bollinger_mean_reversion": bollinger_mean_reversion_signal,
}

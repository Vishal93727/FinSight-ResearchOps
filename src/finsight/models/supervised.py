"""Reproducible chronological supervised-model training and evaluation."""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd

SUPPORTED_FAMILIES = {"ridge", "random_forest", "xgboost", "lightgbm", "lstm"}


@dataclass
class SupervisedEvaluation:
    metrics: dict[str, float | int | str]
    configuration: dict[str, Any]
    model: Any
    train_rows: int
    test_rows: int


def configuration_fingerprint(configuration: dict) -> str:
    payload = json.dumps(configuration, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _make_estimator(family: str, seed: int):
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise ValueError("scikit-learn is required; install the base FinSight dependencies") from exc
    if family == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if family == "random_forest":
        return RandomForestRegressor(n_estimators=160, min_samples_leaf=3, max_features=1.0,
                                     random_state=seed, n_jobs=1)
    if family == "xgboost":
        try:
            from xgboost import XGBRegressor
        except ImportError as exc:
            raise ValueError("xgboost is not installed; install the 'ml' extra") from exc
        return XGBRegressor(n_estimators=180, max_depth=3, learning_rate=0.04,
                            subsample=0.85, colsample_bytree=0.85, objective="reg:squarederror",
                            random_state=seed, n_jobs=1, verbosity=0)
    if family == "lightgbm":
        try:
            from lightgbm import LGBMRegressor
        except ImportError as exc:
            raise ValueError("lightgbm is not installed; install the 'ml' extra") from exc
        return LGBMRegressor(n_estimators=180, max_depth=-1, learning_rate=0.04,
                             num_leaves=15, random_state=seed, n_jobs=1, verbosity=-1)
    raise ValueError("The LSTM family is trained by train_lstm_evaluation")


def train_supervised_evaluation(frame: pd.DataFrame, feature_columns: list[str], target_column: str,
                                date_column: str = "date", model_family: str = "ridge",
                                random_seed: int = 42, test_fraction: float = 0.2) -> SupervisedEvaluation:
    if model_family not in SUPPORTED_FAMILIES - {"lstm"}:
        raise ValueError(f"model_family must be one of {sorted(SUPPORTED_FAMILIES - {'lstm'})}")
    if not feature_columns or target_column in feature_columns:
        raise ValueError("At least one feature is required and target cannot be a feature")
    if len(set(feature_columns)) != len(feature_columns):
        raise ValueError("feature_columns cannot contain duplicates")
    required = set(feature_columns + [target_column, date_column])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    if not 0.1 <= test_fraction <= 0.4:
        raise ValueError("test_fraction must be between 0.10 and 0.40")
    data = frame.loc[:, feature_columns + [target_column, date_column]].copy()
    data[date_column] = pd.to_datetime(data[date_column], errors="coerce")
    for column in feature_columns + [target_column]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna().sort_values(date_column, kind="stable")
    if len(data) < 60:
        raise ValueError("At least 60 valid chronological observations are required")
    split = int(len(data) * (1.0 - test_fraction))
    if split < 40 or len(data) - split < 10:
        raise ValueError("Temporal split must contain at least 40 train and 10 test observations")
    x_train_frame = data.iloc[:split][feature_columns].astype(float)
    x_test_frame = data.iloc[split:][feature_columns].astype(float)
    x_train = x_train_frame.to_numpy(dtype=float)
    x_test = x_test_frame.to_numpy(dtype=float)
    y_train = data.iloc[:split][target_column].to_numpy(dtype=float)
    y_test = data.iloc[split:][target_column].to_numpy(dtype=float)
    if not np.isfinite(x_train).all() or not np.isfinite(x_test).all() or not np.isfinite(y_train).all() or not np.isfinite(y_test).all():
        raise ValueError("Training data must contain only finite numeric values")
    try:
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    except ImportError as exc:
        raise ValueError("scikit-learn is required; install the base FinSight dependencies") from exc
    estimator = _make_estimator(model_family, random_seed)
    estimator.fit(x_train_frame, y_train)
    predictions = np.asarray(estimator.predict(x_test_frame), dtype=float)
    mse = float(mean_squared_error(y_test, predictions))
    direction_actual = np.sign(y_test)
    direction_predicted = np.sign(predictions)
    metrics = {
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": math.sqrt(max(0.0, mse)),
        "r2": float(r2_score(y_test, predictions)) if len(y_test) > 1 else 0.0,
        "directional_accuracy": float(np.mean(direction_actual == direction_predicted)),
        "train_rows": int(len(y_train)), "test_rows": int(len(y_test)),
        "test_start": data.iloc[split][date_column].date().isoformat(),
        "test_end": data.iloc[-1][date_column].date().isoformat(),
    }
    config = {"model_family": model_family, "feature_columns": feature_columns,
              "target_column": target_column, "date_column": date_column,
              "random_seed": int(random_seed), "test_fraction": float(test_fraction),
              "split_method": "chronological_no_shuffle", "valid_rows": int(len(data))}
    return SupervisedEvaluation(metrics=metrics, configuration=config, model=estimator,
                                train_rows=len(y_train), test_rows=len(y_test))


def train_lstm_evaluation(frame: pd.DataFrame, feature_columns: list[str], target_column: str,
                          date_column: str = "date", random_seed: int = 42,
                          test_fraction: float = 0.2, sequence_length: int = 12, epochs: int = 35) -> SupervisedEvaluation:
    """Small CPU PyTorch LSTM benchmark, chronologically split and intentionally bounded."""
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise ValueError("PyTorch is required for the LSTM model family") from exc
    if not 0.1 <= test_fraction <= 0.4:
        raise ValueError("test_fraction must be between 0.10 and 0.40")
    if not 5 <= sequence_length <= 60 or not 5 <= epochs <= 50:
        raise ValueError("sequence_length must be 5-60 and epochs 5-50")
    if not feature_columns or target_column in feature_columns or len(set(feature_columns)) != len(feature_columns):
        raise ValueError("Provide unique features that exclude the target")
    required = set(feature_columns + [target_column, date_column])
    if required - set(frame.columns):
        raise ValueError("Required date, feature or target columns are missing")
    data = frame.loc[:, feature_columns + [target_column, date_column]].copy()
    data[date_column] = pd.to_datetime(data[date_column], errors="coerce")
    for col in feature_columns + [target_column]: data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna().sort_values(date_column, kind="stable")
    if len(data) < 100: raise ValueError("At least 100 valid rows are required for LSTM evaluation")
    if len(data) > 20_000: raise ValueError("LSTM evaluation is bounded to 20,000 rows per synchronous request")
    x = data[feature_columns].to_numpy(dtype=np.float32)
    y = data[target_column].to_numpy(dtype=np.float32)
    split_row = int(len(data) * (1.0 - test_fraction))
    # Fit scaling only on the training portion.
    mean = x[:split_row].mean(axis=0); std = x[:split_row].std(axis=0); std[std < 1e-8] = 1.0
    x = (x - mean) / std
    seq_x, seq_y, seq_dates = [], [], []
    for i in range(sequence_length, len(data)):
        seq_x.append(x[i-sequence_length:i]); seq_y.append(y[i]); seq_dates.append(i)
    sx, sy, sidx = np.asarray(seq_x), np.asarray(seq_y), np.asarray(seq_dates)
    train_mask = sidx < split_row; test_mask = ~train_mask
    if train_mask.sum() < 50 or test_mask.sum() < 10: raise ValueError("Insufficient train/test sequences")
    torch.manual_seed(random_seed); torch.use_deterministic_algorithms(True, warn_only=True)
    class _LSTM(nn.Module):
        def __init__(self, feature_count: int):
            super().__init__(); self.lstm = nn.LSTM(feature_count, 24, batch_first=True)
            self.head = nn.Linear(24, 1)
        def forward(self, values):
            out, _ = self.lstm(values); return self.head(out[:, -1, :]).squeeze(-1)
    model = _LSTM(len(feature_columns))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    loss_fn = nn.MSELoss()
    tx = torch.tensor(sx[train_mask]); ty = torch.tensor(sy[train_mask])
    model.train()
    for _ in range(epochs):
        optimizer.zero_grad(); loss = loss_fn(model(tx), ty); loss.backward(); optimizer.step()
    model.eval()
    with torch.no_grad(): predictions = model(torch.tensor(sx[test_mask])).numpy()
    actual = sy[test_mask]
    mse = float(np.mean((actual - predictions) ** 2))
    from sklearn.metrics import r2_score
    metrics = {"mae": float(np.mean(np.abs(actual - predictions))), "rmse": math.sqrt(max(0.0, mse)),
               "r2": float(r2_score(actual, predictions)),
               "directional_accuracy": float(np.mean(np.sign(actual) == np.sign(predictions))),
               "train_rows": int(train_mask.sum()), "test_rows": int(test_mask.sum()),
               "test_start": data.iloc[sidx[test_mask][0]][date_column].date().isoformat(),
               "test_end": data.iloc[-1][date_column].date().isoformat()}
    config = {"model_family": "lstm", "feature_columns": feature_columns, "target_column": target_column,
              "date_column": date_column, "random_seed": random_seed, "test_fraction": test_fraction, "sequence_length": sequence_length,
              "epochs": epochs, "split_method": "chronological_no_shuffle",
              "scaler_mean": mean.tolist(), "scaler_std": std.tolist()}
    return SupervisedEvaluation(metrics=metrics, configuration=config, model=model,
                                train_rows=int(train_mask.sum()), test_rows=int(test_mask.sum()))

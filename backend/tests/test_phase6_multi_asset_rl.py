"""Multi-asset allocation environment: limits, execution timing, rewards, baselines, evaluation."""
import numpy as np
import pytest

from finsight.reinforcement_learning.environments.multi_asset_env import MultiAssetPortfolioEnv
from finsight.reinforcement_learning.evaluation.portfolio import (
    buy_and_hold_policy, equal_weight_policy, evaluate_baselines, portfolio_metrics, run_allocation,
    train_and_evaluate_portfolio)
from finsight.reinforcement_learning.rewards.reward_schemes import RewardConfig, compute_reward
from finsight.risk.allocation import AllocationLimits, constrain_weights, validate_allocation


def _prices(bars: int = 120, assets: int = 3, seed: int = 0):
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, (bars, assets)), axis=0))
    opens = np.vstack([closes[:1], closes[:-1]]) * (1 + rng.normal(0, 0.001, (bars, assets)))
    return opens, closes


def _env(**kwargs) -> MultiAssetPortfolioEnv:
    opens, closes = _prices()
    kwargs.setdefault("fee_bps", 0.0)
    kwargs.setdefault("slippage_bps", 0.0)
    return MultiAssetPortfolioEnv(opens, closes, **kwargs)


# --- deterministic allocation limits -------------------------------------------------------

def test_constraints_cap_positions_scale_exposure_and_keep_cash_non_negative():
    limits = AllocationLimits(max_position_weight=0.30, max_gross_exposure=0.80)
    allowed = constrain_weights(np.array([0.9, 0.5, 0.4, 0.0]), limits)
    assert validate_allocation(allowed, limits) == []
    assert allowed[:-1].max() <= 0.30 + 1e-12 and allowed[:-1].sum() <= 0.80 + 1e-12


def test_random_proposals_never_escape_the_limits():
    rng = np.random.default_rng(7)
    limits = AllocationLimits(0.35, 0.90)
    for _ in range(300):
        proposal = rng.normal(0.3, 1.0, 5)
        proposal[rng.integers(0, 5)] = rng.choice([np.nan, np.inf, -np.inf, 5.0])
        assert validate_allocation(constrain_weights(proposal, limits), limits) == []


def test_validation_reports_each_kind_of_violation():
    limits = AllocationLimits(0.40, 1.0)
    assert any("short" in p for p in validate_allocation(np.array([-0.1, 0.5, 0.6]), limits))
    assert any("position" in p for p in validate_allocation(np.array([0.7, 0.0, 0.3]), limits))
    assert any("sum" in p for p in validate_allocation(np.array([0.2, 0.2, 0.2]), limits))
    with pytest.raises(ValueError):
        AllocationLimits(max_gross_exposure=1.5)


# --- environment timing and constraints ----------------------------------------------------

def test_trade_is_filled_at_next_open_and_never_on_the_decision_bar():
    opens = np.full((60, 1), 100.0)
    closes = opens.copy()
    opens[22:] = 200.0  # the only price move: open(t+1)=100 -> open(t+2)=200 at the first step (t=20)
    env = MultiAssetPortfolioEnv(opens, closes, limits=AllocationLimits(1.0, 1.0), fee_bps=0, slippage_bps=0)
    env.reset()
    _, _, _, _, info = env.apply_target_weights(np.array([1.0, 0.0]))
    assert info["equity"] == pytest.approx(2.0)


def test_observation_uses_only_information_through_the_decision_bar():
    opens, closes = _prices()
    altered = closes.copy()
    start = MultiAssetPortfolioEnv(opens, closes).start
    altered[start + 1:] *= 3.0
    first, _ = MultiAssetPortfolioEnv(opens, closes).reset()
    second, _ = MultiAssetPortfolioEnv(opens, altered).reset()
    assert np.allclose(first, second)


def test_any_action_is_constrained_inside_the_environment():
    env = _env(limits=AllocationLimits(0.30, 1.0))
    env.reset()
    rng = np.random.default_rng(1)
    done = False
    while not done:
        _, _, done, _, info = env.step(rng.uniform(-1, 1, env.n_assets + 1))
        assert validate_allocation(np.array(info["target_weights"]), env.limits) == []
    proposal = np.array([1.0, 0.0, 0.0, 0.0])
    env.reset()
    _, _, _, _, info = env.apply_target_weights(proposal)
    assert info["target_weights"][0] == pytest.approx(0.30) and info["target_weights"][-1] == pytest.approx(0.70)


def test_costs_reduce_equity_and_holding_the_same_target_costs_less_than_trading_into_it():
    cheap = _env(fee_bps=0, slippage_bps=0)
    costly = _env(fee_bps=10, slippage_bps=10)
    for env in (cheap, costly):
        env.reset()
    target = np.array([0.3, 0.3, 0.3, 0.1])
    _, _, _, _, a = cheap.apply_target_weights(target)
    _, _, _, _, b = costly.apply_target_weights(target)
    assert b["cost"] > 0 and b["equity"] < a["equity"]
    _, _, _, _, again = costly.apply_target_weights(np.array(b["target_weights"]))
    assert again["turnover"] < b["turnover"]


def test_invalid_inputs_are_rejected():
    opens, closes = _prices()
    with pytest.raises(ValueError):
        MultiAssetPortfolioEnv(opens[:10], closes[:10])
    bad = closes.copy()
    bad[5, 0] = -1.0
    with pytest.raises(ValueError):
        MultiAssetPortfolioEnv(opens, bad)
    with pytest.raises(ValueError):
        MultiAssetPortfolioEnv(opens, closes[:, :2])


def test_environment_passes_the_gymnasium_checker():
    pytest.importorskip("gymnasium")
    check_env = pytest.importorskip("stable_baselines3.common.env_checker").check_env
    check_env(_env(), warn=True)


# --- rewards -------------------------------------------------------------------------------

def test_reward_schemes_follow_their_definitions():
    kwargs = {"log_return": 0.01, "cost": 0.001, "turnover": 0.5, "drawdown": 0.05, "recent_net_returns": [0.01] * 3}
    assert compute_reward(RewardConfig("log_return"), **kwargs) == pytest.approx(0.01)
    plan = compute_reward(RewardConfig("cost_turnover_drawdown", 1.0, 0.001, 0.10), **kwargs)
    assert plan == pytest.approx(0.01 - 0.001 - 0.0005 - 0.005)
    assert compute_reward(RewardConfig("risk_adjusted"), **kwargs) == pytest.approx(0.01)  # too little history
    long_history = dict(kwargs, recent_net_returns=[0.01, -0.01, 0.02, 0.0, 0.01, 0.0])
    assert compute_reward(RewardConfig("risk_adjusted", window=6), **long_history) == pytest.approx(
        np.mean(long_history["recent_net_returns"]) / np.std(long_history["recent_net_returns"]))
    with pytest.raises(ValueError):
        RewardConfig("moon_shot")
    with pytest.raises(ValueError):
        RewardConfig(lambda_cost=-1.0)


# --- metrics and baselines -----------------------------------------------------------------

def test_metrics_match_known_values():
    equity = np.array([1.0, 1.1, 0.99, 1.0890])
    rets = equity[1:] / equity[:-1] - 1
    metrics = portfolio_metrics(equity, rets, turnover=0.5)
    assert metrics["total_return"] == pytest.approx(0.089)
    assert metrics["max_drawdown"] == pytest.approx(0.99 / 1.1 - 1)
    assert metrics["turnover"] == 0.5 and metrics["observations"] == 3


def test_baselines_share_the_environment_and_buy_and_hold_never_rebalances():
    opens, closes = _prices(bars=200)
    env_bh = MultiAssetPortfolioEnv(opens, closes, fee_bps=5, slippage_bps=5)
    env_ew = MultiAssetPortfolioEnv(opens, closes, fee_bps=5, slippage_bps=5)
    hold = run_allocation(env_bh, buy_and_hold_policy)["metrics"]
    equal = run_allocation(env_ew, equal_weight_policy)["metrics"]
    assert hold["observations"] == equal["observations"]
    assert equal["turnover"] > hold["turnover"]
    assert hold["turnover"] == pytest.approx(1.0, abs=1e-9)  # the initial purchase of the full portfolio
    assert set(evaluate_baselines(opens, closes)) == {"equal_weight", "buy_and_hold"}


# --- training and out-of-sample evaluation -------------------------------------------------

def test_training_requires_valid_settings_before_importing_anything_heavy():
    opens, closes = _prices()
    with pytest.raises(ValueError):
        train_and_evaluate_portfolio(opens, closes, "DQN")
    with pytest.raises(ValueError):
        train_and_evaluate_portfolio(opens, closes, "PPO", seeds=(1, 1))
    with pytest.raises(ValueError):
        train_and_evaluate_portfolio(opens, closes, "PPO", train_fraction=0.2)


@pytest.mark.parametrize("algorithm", ["PPO", "SAC"])
def test_policy_is_evaluated_out_of_sample_over_seeds_beside_the_baselines(algorithm):
    pytest.importorskip("stable_baselines3")
    opens, closes = _prices(bars=160)
    result = train_and_evaluate_portfolio(opens, closes, algorithm, seeds=(0, 1), total_timesteps=256)
    assert result["out_of_sample"] is True
    assert [row["seed"] for row in result["per_seed"]] == [0, 1]
    assert set(result["baselines"]) == {"equal_weight", "buy_and_hold"}
    assert result["summary"]["seed_count"] == 2
    assert 0 <= result["summary"]["seeds_beating_equal_weight"] <= 2
    assert result["configuration"]["split_index"] == int(160 * 0.70)
    assert len(result["configuration_sha256"]) == 64
    assert all(row["observations"] == result["baselines"]["equal_weight"]["observations"]
               for row in result["per_seed"])
